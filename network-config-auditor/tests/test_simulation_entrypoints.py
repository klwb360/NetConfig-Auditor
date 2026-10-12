from contextlib import redirect_stderr, redirect_stdout
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from netaudit.cli import main
from netaudit.server import LocalServer, make_handler


BACKUP = 'hostname Lab\r\n! synthetic fixture\r\ninterface GigabitEthernet0/1\r\n description original\r\n!\r\ncustom-preserve value\r\nend\r\n'
SCRIPT = 'configure terminal\nvlan 20\nexit\ninterface GigabitEthernet0/1\nswitchport mode access\nswitchport access vlan 20\nend'


class SimulationCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='练习 CLI ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backup = self.root / '原始 备份.cfg'
        self.backup.write_bytes(BACKUP.encode())

    def run_cli(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch('netaudit.cli.audit_configuration', side_effect=AssertionError('audit must be optional')):
            code = main(args)
        self.assertEqual(self.backup.read_bytes(), BACKUP.encode())
        return code, out.getvalue(), err.getvalue()

    def test_plan_is_local_and_does_not_apply(self):
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('unexpected network')):
            code, output, _ = self.run_cli(['plan', str(self.backup), '--goal', '创建 VLAN 20'])
        value = json.loads(output)
        self.assertEqual((code, value['status']), (0, 'ready'))
        self.assertNotIn('config', value)
        self.assertIn('vlan 20', value['commands'])

    def test_missing_goal_parameters_use_exit_two(self):
        code, output, _ = self.run_cli(['plan', str(self.backup), '--goal', '创建 VLAN'])
        self.assertEqual((code, json.loads(output)['status']), (2, 'needs-input'))

    def test_commands_file_export_preserves_crlf_and_unknown_lines(self):
        commands = self.root / '练习 命令.txt'
        commands.write_bytes(SCRIPT.encode())
        dest = self.root / '模拟 副本.cfg'
        code, output, _ = self.run_cli(['simulate', str(self.backup), '--commands', str(commands), '--out', str(dest)])
        value = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual(dest.read_bytes(), value['config'].encode())
        self.assertIn(b'custom-preserve value\r\n', dest.read_bytes())
        self.assertNotIn(b'\n', dest.read_bytes().replace(b'\r\n', b''))
        self.assertIn('switchport access vlan 20', value['config'])

    def test_failed_batch_does_not_replace_existing_output(self):
        dest = self.root / '已有 文件.cfg'
        dest.write_bytes(b'keep me')
        code, output, _ = self.run_cli(['simulate', str(self.backup), '--command', SCRIPT,
                                      '--command', 'unknown-command', '--out', str(dest)])
        value = json.loads(output)
        self.assertEqual(code, 2)
        self.assertTrue(value['summary']['rolled_back'])
        self.assertEqual(value['config'], BACKUP)
        self.assertEqual(dest.read_bytes(), b'keep me')

    def test_output_protects_each_input_before_simulation(self):
        commands, context = self.root / 'commands', self.root / 'context'
        commands.write_text(SCRIPT)
        context.write_text('{"mode":"exec","target":""}')
        for dest in (self.backup, commands, context):
            with self.subTest(dest=dest.name), patch('netaudit.simulator.simulate_configuration') as simulate:
                code, _, error = self.run_cli(['simulate', str(self.backup), '--commands', str(commands),
                                              '--context', str(context), '--out', str(dest)])
                self.assertEqual(code, 2)
                self.assertIn('不能覆盖', error)
                simulate.assert_not_called()

    def test_context_continues_interface_mode(self):
        context = self.root / 'context.json'
        context.write_text('{"mode":"interface","target":"GigabitEthernet0/1"}')
        code, output, _ = self.run_cli(['simulate', str(self.backup), '--context', str(context), '--command', 'shutdown'])
        self.assertEqual(code, 0)
        self.assertIn(' shutdown', json.loads(output)['config'])

    def test_oversized_command_file_fails_without_output(self):
        commands = self.root / 'commands'
        commands.write_bytes(b'a' * 65537)
        dest = self.root / 'out.cfg'
        code, _, error = self.run_cli(['simulate', str(self.backup), '--commands', str(commands), '--out', str(dest)])
        self.assertEqual(code, 2)
        self.assertIn('64 KiB', error)
        self.assertFalse(dest.exists())


class SimulationAPITests(unittest.TestCase):
    def setUp(self):
        self.server = LocalServer(('127.0.0.1', 0), make_handler('simulation-token'))
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())

    def request(self, path, data=None, headers=None, method='POST'):
        port = self.server.server_port
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        request_headers = {'Origin': f'http://127.0.0.1:{port}', 'X-NetAudit-Token': 'simulation-token', 'Content-Type': 'application/json'}
        request_headers.update(headers or {})
        try:
            connection.request(method, path, None if data is None else json.dumps(data), request_headers)
            response = connection.getresponse()
            raw = response.read().decode()
            return response.status, raw if method == 'GET' else json.loads(raw)
        finally:
            connection.close()

    def test_fourth_web_resource_and_security_headers(self):
        status, script = self.request('/simulator.js', method='GET')
        self.assertEqual(status, 200)
        self.assertIn('NetAuditBridge', script)

    def test_practice_endpoints_never_call_audit_or_ai(self):
        with patch('netaudit.server.audit_configuration', side_effect=AssertionError('optional audit')):
            status, planned = self.request('/api/plan', {'config': BACKUP, 'goal': '创建 VLAN 20'})
            self.assertEqual((status, planned['status']), (200, 'ready'))
            status, result = self.request('/api/simulate', {'config': BACKUP, 'commands': SCRIPT, 'ai': {'enabled': True}})
            self.assertEqual(status, 200)
            self.assertFalse(result['summary']['rolled_back'])
            self.assertNotIn('report', result)
        status, audited = self.request('/api/audit', {'config': result['config']})
        self.assertEqual(status, 200)
        self.assertEqual(set(audited['exports']), {'json', 'md', 'html'})

    def test_routes_keep_origin_token_and_host_protection(self):
        for path in ('/api/simulate', '/api/plan'):
            for headers in ({'Origin': 'https://example.org'}, {'X-NetAudit-Token': ''}, {'Host': 'evil.example'}):
                with self.subTest(path=path, headers=headers):
                    status, _ = self.request(path, {'config': BACKUP}, headers)
                    self.assertEqual(status, 403)

    def test_bad_request_types_produce_readable_error(self):
        for value in ([], {'config': []}, {'config': BACKUP, 'commands': []},
                      {'config': BACKUP, 'context': {'mode': [], 'target': ''}},
                      {'config': BACKUP, 'context': {'mode': 'exec', 'target': []}},
                      {'config': BACKUP, 'vendor': []}):
            with self.subTest(value=value):
                status, result = self.request('/api/simulate', value)
                self.assertEqual(status, 400)
                self.assertIsInstance(result['error'], str)
        status, _ = self.request('/api/plan', {'config': BACKUP, 'goal': []})
        self.assertEqual(status, 400)

    def test_server_is_stateless_between_clients_and_rolls_back(self):
        status, result = self.request('/api/simulate', {'config': BACKUP, 'commands': SCRIPT + '\nunknown-command'})
        self.assertEqual(status, 200)
        self.assertTrue(result['summary']['rolled_back'])
        self.assertEqual(result['config'], BACKUP)
        self.assertEqual(result['context'], {'mode': 'exec', 'target': ''})
        _, other = self.request('/api/simulate', {'config': BACKUP})
        self.assertEqual(other['config'], BACKUP)
        self.assertFalse(other['summary']['changed'])


if __name__ == '__main__':
    unittest.main()
