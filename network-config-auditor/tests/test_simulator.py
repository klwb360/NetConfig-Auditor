import json
import unittest

from netaudit.parser import parse_config
from netaudit.simulator import (MAX_COMMAND_BYTES, MAX_COMMAND_LINES,
                                MAX_OUTPUT_BYTES, simulate_configuration)


VENDORS = ('cisco', 'ruijie', 'huawei', 'h3c')


def fixture(vendor='cisco', interface='', extra='', newline='\n'):
    ios = vendor in ('cisco', 'ruijie')
    header = {'cisco': 'hostname Lab', 'ruijie': 'version RGOS\nhostname Lab',
              'huawei': '!Software Version VRP\nsysname Lab',
              'h3c': '# H3C Comware\nsysname Lab'}[vendor]
    sep = '!' if ios else '#'
    vty = 'line vty 0 4' if ios else 'user-interface vty 0 4'
    parts = [header, sep, 'vlan 1', sep, 'vlan 10', sep,
             'interface Gi0/1', interface, sep, 'interface Gi0/2',
             ' description existing', sep, vty, ' description management',
             sep, extra, 'end' if ios else 'return']
    return '\n'.join(s for s in parts if s) .replace('\n', newline) + newline


def run(config, commands, vendor='cisco'):
    ios = vendor in ('cisco', 'ruijie')
    return simulate_configuration(config, vendor, ('configure terminal' if ios else 'system-view') + '\n' + commands)


class SimulatorTests(unittest.TestCase):
    def assertApplied(self, result):
        self.assertFalse(result['summary']['rolled_back'], result['results'])
        self.assertEqual(result['summary']['blocked'], 0)
        self.assertEqual(result['summary']['unsupported'], 0)
        self.assertEqual(result['summary']['invalid'], 0)

    def assertRejected(self, result, original):
        self.assertTrue(result['summary']['rolled_back'], result['results'])
        self.assertEqual(result['config'], original)
        self.assertEqual(result['diff'], '')
        self.assertEqual(result['summary']['applied'], 0)

    def test_cisco_complete_practice(self):
        self.complete_practice('cisco')

    def test_ruijie_complete_practice(self):
        self.complete_practice('ruijie')

    def test_huawei_complete_practice(self):
        self.complete_practice('huawei')

    def test_h3c_complete_practice(self):
        self.complete_practice('h3c')

    def complete_practice(self, vendor):
        ios = vendor in ('cisco', 'ruijie')
        back = 'exit' if ios else 'quit'
        end = 'end' if ios else 'return'
        acl = 'ip access-list extended LAB' if ios else 'acl number 3000'
        rule = '10 permit tcp any any eq 443' if ios else 'rule 10 permit tcp destination-port eq 443'
        binding = 'ip access-group LAB in' if ios else 'traffic-filter inbound acl 3000' if vendor == 'huawei' else 'packet-filter 3000 inbound'
        mode = 'switchport mode access' if ios else 'port link-type access'
        access = 'switchport access vlan 20' if ios else 'port default vlan 20' if vendor == 'huawei' else 'port access vlan 20'
        route = 'ip route 198.51.100.0 255.255.255.0 192.0.2.254' if ios else 'ip route-static 198.51.100.0 255.255.255.0 192.0.2.254'
        cmds = ['vlan 20', 'name Practice' if ios else 'description Practice', back,
                acl, rule, back, 'interface Gi0/1', 'description Learning', mode,
                access, binding, 'shutdown', 'no shutdown' if ios else 'undo shutdown',
                back, 'interface Gi0/2', 'ip address 192.0.2.1 255.255.255.0', back,
                route, 'line vty 0 4' if ios else 'user-interface vty 0 4',
                'transport input ssh' if ios else 'protocol inbound ssh',
                'exec-timeout 10 0' if ios else 'idle-timeout 10 0', end,
                'show running-config' if ios else 'display current-configuration']
        result = run(fixture(vendor), '\n'.join(cmds), vendor)
        self.assertApplied(result)
        cfg = parse_config(result['config'], vendor)
        self.assertEqual(cfg.interfaces['Gi0/1'].access_vlan, 20)
        self.assertEqual(cfg.interfaces['Gi0/1'].mode, 'access')
        self.assertEqual(cfg.interfaces['Gi0/1'].shutdown, False)
        self.assertEqual(cfg.interfaces['Gi0/2'].addresses, ['192.0.2.1/24'])
        self.assertEqual(cfg.management_lines[0].transport, ['ssh'])
        self.assertEqual(cfg.management_lines[0].idle_seconds, 600)
        self.assertEqual(cfg.routes[0].destination, '198.51.100.0/24')
        self.assertEqual(result['context'], {'mode': 'exec', 'target': ''})
        self.assertIn('Learning', result['results'][-1]['output'])

    def test_backup_is_byte_preserved_with_no_commands(self):
        for vendor in VENDORS:
            with self.subTest(vendor=vendor):
                config = fixture(vendor, extra='unknown-command keep-me\n! literal trailing  ', newline='\r\n').rstrip('\r\n')
                result = simulate_configuration(config, vendor)
                self.assertApplied(result)
                self.assertEqual(result['config'], config)
                self.assertFalse(result['summary']['changed'])

    def test_change_preserves_unknown_stanzas_and_crlf(self):
        original = fixture(interface=' custom-feature abc\n description Old', extra='router weird 5\n  nested private-value\n!', newline='\r\n')
        result = run(original, 'interface Gi0/1\ndescription New')
        self.assertApplied(result)
        self.assertEqual(result['config'], original.replace(' description Old', ' description New'))

    def test_whole_batch_rolls_back_context_and_config(self):
        config = fixture()
        result = run(config, 'vlan 20\nexit\ninterface Gi0/1\ndescription Changed\nshow running-config\nreload')
        self.assertRejected(result, config)
        self.assertEqual(result['context'], {'mode': 'exec', 'target': ''})
        self.assertTrue(all(r['rolled_back'] for r in result['results'][:-1]))
        self.assertNotIn('Changed', result['results'][-2]['output'])

    def test_failure_restores_caller_context(self):
        config = fixture()
        context = {'mode': 'interface', 'target': 'Gi0/1'}
        result = simulate_configuration(config, 'cisco', 'description New\nquit', context)
        self.assertRejected(result, config)
        self.assertEqual(result['context'], context)
        self.assertEqual(context, {'mode': 'interface', 'target': 'Gi0/1'})

    def test_interface_requires_existing_full_name(self):
        config = fixture()
        for command in ('interface Gi9/99', 'interface range Gi0/1-2', 'interface Vlan20'):
            with self.subTest(command=command):
                self.assertRejected(run(config, command), config)

    def test_wrong_mode_rejected(self):
        config = fixture()
        self.assertRejected(simulate_configuration(config, 'cisco', 'shutdown'), config)
        self.assertRejected(run(config, 'interface Gi0/1\nvlan 20'), config)

    def test_wrong_vendor_commands_rejected(self):
        for vendor in VENDORS:
            config = fixture(vendor)
            command = 'system-view' if vendor in ('cisco', 'ruijie') else 'configure terminal'
            with self.subTest(vendor=vendor):
                self.assertRejected(simulate_configuration(config, vendor, command), config)

    def test_duplicate_interface_blocks_rejected(self):
        config = fixture(extra='interface Gi0/1\n description duplicate\n!')
        self.assertRejected(run(config, 'interface Gi0/1\ndescription bad'), config)

    def test_unindented_huawei_child_scope_rejected(self):
        config = fixture('huawei', interface='description no-indent')
        self.assertRejected(run(config, 'interface Gi0/1\ndescription bad', 'huawei'), config)

    def test_nonios_global_edit_rejects_unseparated_interface_scope(self):
        for vendor in ('huawei', 'h3c'):
            config = 'sysname Lab\n#\ninterface Gi0/1\nstp enable\n#\n'
            self.assertRejected(run(config, 'stp disable', vendor), config)

    def test_nonios_global_edit_rejects_unseparated_unknown_scope(self):
        for vendor in ('huawei', 'h3c'):
            config = 'sysname Lab\n#\nunknown-feature\nstp enable\n#\n'
            self.assertRejected(run(config, 'stp disable', vendor), config)

    def test_nonios_global_edit_rejects_unseparated_aaa_scope(self):
        config = 'sysname Lab\n#\naaa\nstp enable\n#\n'
        self.assertRejected(run(config, 'stp disable', 'huawei'), config)

    def test_nonios_global_edit_accepts_flat_known_commands(self):
        for vendor in ('huawei', 'h3c'):
            config = 'sysname Lab\nversion 7.1\nstp enable\n#\n'
            result = run(config, 'stp disable', vendor)
            self.assertApplied(result)
            self.assertFalse(result['inventory']['stp']['enabled'])

    def test_nested_unknown_block_rejected(self):
        config = fixture(interface=' description original\n  nested child')
        self.assertRejected(run(config, 'interface Gi0/1\ndescription bad'), config)

    def test_unclosed_banner_rejected(self):
        config = fixture(extra='banner motd @\nprivate text')
        self.assertRejected(run(config, 'vlan 20'), config)

    def test_banner_preserved_without_editing_its_commands(self):
        banner = 'banner motd @\ninterface Gi0/9\n password 0 banner-secret\n@\n!'
        config = fixture(extra=banner)
        result = run(config, 'interface Gi0/1\ndescription New')
        self.assertApplied(result)
        self.assertIn(banner, result['config'])
        self.assertNotIn('Gi0/9', result['inventory']['interfaces'])

    def test_create_and_delete_vlan_range_preserves_other_vlans(self):
        for vendor, header, remove in [('huawei', 'vlan batch 20 to 23', 'undo vlan batch 21 to 22'), ('ruijie', 'vlan range 20-23', 'no vlan range 21-22')]:
            with self.subTest(vendor=vendor):
                config = fixture(vendor, extra=header + '\n' + ('!' if vendor == 'ruijie' else '#'))
                result = run(config, remove, vendor)
                self.assertApplied(result)
                self.assertEqual(set(parse_config(result['config'], vendor).vlans), {1, 10, 20, 23})

    def test_vlan_range_create_leaves_global_view(self):
        for vendor, command in [('huawei', 'vlan batch 20 to 23'), ('ruijie', 'vlan range 20-23')]:
            result = run(fixture(vendor), command, vendor)
            self.assertApplied(result)
            self.assertEqual(result['context']['mode'], 'config')
            self.assertTrue({20, 21, 22, 23} <= set(result['inventory']['vlans']))

    def test_vlan_range_name_edit_rejected(self):
        config = fixture('ruijie', extra='vlan range 20-23\n!')
        self.assertRejected(run(config, 'vlan 20\nname dangerous', 'ruijie'), config)

    def test_vlan_creation_does_not_accept_all_or_none(self):
        for vendor, command in [('huawei', 'vlan batch all'), ('huawei', 'vlan batch none'), ('ruijie', 'vlan range all'), ('ruijie', 'vlan range none')]:
            config = fixture(vendor)
            with self.subTest(vendor=vendor, command=command):
                self.assertRejected(run(config, command, vendor), config)

    def test_vlan_reference_must_exist(self):
        config = fixture(interface=' switchport mode access')
        self.assertRejected(run(config, 'interface Gi0/1\nswitchport access vlan 20'), config)

    def test_vlan_access_requires_mode(self):
        config = fixture()
        self.assertRejected(run(config, 'interface Gi0/1\nswitchport access vlan 10'), config)

    def test_vlan_delete_with_references_blocked(self):
        for line in (' switchport access vlan 10', ' switchport trunk native vlan 10', ' switchport trunk allowed vlan 10'):
            config = fixture(interface=line)
            with self.subTest(line=line):
                self.assertRejected(run(config, 'no vlan 10'), config)
        config = fixture(extra='interface Vlan10\n ip address 192.0.2.1 255.255.255.0\n!')
        self.assertRejected(run(config, 'no vlan 10'), config)

    def test_default_vlan_delete_rejected(self):
        config = fixture()
        self.assertRejected(run(config, 'no vlan 1'), config)

    def test_vlan_unknown_dependency_blocked(self):
        config = fixture(extra='unknown vlan 10 something')
        self.assertRejected(run(config, 'no vlan 10'), config)

    def test_vlan_unknown_hybrid_range_dependency_blocked(self):
        for vendor, line in [('huawei', 'port hybrid tagged vlan 5 to 20'), ('h3c', 'port hybrid vlan 5 to 20 tagged')]:
            config = fixture(vendor, interface=' port link-type hybrid\n ' + line)
            self.assertRejected(run(config, 'undo vlan 10', vendor), config)

    def test_vlan_unknown_subconfiguration_not_deleted(self):
        config = fixture().replace('vlan 10\n!', 'vlan 10\n proprietary secret-value\n!')
        self.assertRejected(run(config, 'no vlan 10'), config)

    def test_vlan_delete_is_idempotent(self):
        result = run(fixture(), 'no vlan 10\nno vlan 10')
        self.assertApplied(result)
        self.assertEqual(result['results'][-1]['status'], 'noop')
        self.assertNotIn(10, result['inventory']['vlans'])

    def test_cisco_trunk_repeated_add_remove_has_final_semantics(self):
        config = fixture(interface=' switchport mode trunk\n switchport trunk allowed vlan 10\n switchport trunk allowed vlan remove 10')
        result = run(config, 'interface Gi0/1\nswitchport trunk allowed vlan add 10\nswitchport trunk allowed vlan remove 10\nswitchport trunk allowed vlan remove 10')
        self.assertApplied(result)
        self.assertEqual(result['inventory']['interfaces']['Gi0/1']['allowed_vlan_ranges'], [])
        self.assertEqual(result['results'][-1]['status'], 'noop')

    def test_nonios_trunk_repeated_add_remove_has_final_semantics(self):
        for vendor, prefix in [('huawei', 'port trunk allow-pass vlan '), ('h3c', 'port trunk permit vlan ')]:
            with self.subTest(vendor=vendor):
                config = fixture(vendor, interface=' port link-type trunk\n ' + prefix + '10\n undo ' + prefix + '10')
                result = run(config, 'interface Gi0/1\n' + prefix + '10\nundo ' + prefix + '10\n' + prefix + '10', vendor)
                self.assertApplied(result)
                self.assertEqual(result['inventory']['interfaces']['Gi0/1']['allowed_vlan_ranges'], [[1, 1], [10, 10]])

    def test_nonios_trunk_explicit_full_replacement(self):
        for vendor, prefix in [('huawei', 'port trunk allow-pass vlan '), ('h3c', 'port trunk permit vlan ')]:
            config = fixture(vendor, interface=' port link-type trunk')
            result = run(config, 'interface Gi0/1\nundo ' + prefix + '1 to 4094\n' + prefix + '10', vendor)
            self.assertApplied(result)
            self.assertEqual(result['inventory']['interfaces']['Gi0/1']['allowed_vlan_ranges'], [[10, 10]])

    def test_access_inverse_cannot_override_replayed_command(self):
        config = fixture(interface=' switchport mode access\n switchport access vlan 10\n no switchport access vlan')
        result = run(config, 'interface Gi0/1\nswitchport access vlan 10')
        self.assertApplied(result)
        self.assertEqual(result['inventory']['interfaces']['Gi0/1']['access_vlan'], 10)

    def test_ip_inverse_cannot_override_replayed_command(self):
        config = fixture(interface=' ip address 192.0.2.1 255.255.255.0\n no ip address')
        result = run(config, 'interface Gi0/1\nip address 192.0.2.2 255.255.255.0')
        self.assertApplied(result)
        self.assertEqual(result['inventory']['interfaces']['Gi0/1']['addresses'], ['192.0.2.2/24'])

    def test_primary_address_change_preserves_secondary(self):
        config = fixture(interface=' ip address 192.0.2.1 255.255.255.0\n ip address 198.51.100.1 255.255.255.0 secondary')
        result = run(config, 'interface Gi0/1\nip address 192.0.2.2 255.255.255.0')
        self.assertApplied(result)
        self.assertEqual(result['inventory']['interfaces']['Gi0/1']['addresses'], ['192.0.2.2/24', '198.51.100.1/24'])

    def test_secondary_requires_real_primary(self):
        for initial in ('', ' ip address 192.0.2.1 255.255.255.0 secondary'):
            config = fixture(interface=initial)
            self.assertRejected(run(config, 'interface Gi0/1\nip address 198.51.100.1 255.255.255.0 secondary'), config)

    def test_secondary_requires_primary_after_equivalent_mask_removal(self):
        config = fixture('huawei', interface=' ip address 192.0.2.1 255.255.255.0\n ip address 198.51.100.1 255.255.255.0 sub\n undo ip address 192.0.2.1 24')
        self.assertRejected(run(config, 'interface Gi0/1\nip address 203.0.113.1 255.255.255.0 sub', 'huawei'), config)

    def test_secondary_keyword_must_match_vendor(self):
        config = fixture(interface=' ip address 192.0.2.1 255.255.255.0')
        self.assertRejected(run(config, 'interface Gi0/1\nip address 198.51.100.1 255.255.255.0 sub'), config)

    def test_existing_address_role_mismatch_is_not_noop(self):
        for vendor in VENDORS:
            suffix = 'secondary' if vendor in ('cisco', 'ruijie') else 'sub'
            config = fixture(vendor, interface=' ip address 192.0.2.1 255.255.255.0\n ip address 198.51.100.1 255.255.255.0 ' + suffix)
            for command in ('ip address 198.51.100.1 255.255.255.0', 'ip address 192.0.2.1 255.255.255.0 ' + suffix):
                with self.subTest(vendor=vendor, command=command):
                    self.assertRejected(run(config, 'interface Gi0/1\n' + command, vendor), config)

    def test_existing_address_same_role_is_noop(self):
        for vendor in VENDORS:
            suffix = 'secondary' if vendor in ('cisco', 'ruijie') else 'sub'
            config = fixture(vendor, interface=' ip address 192.0.2.1 255.255.255.0\n ip address 198.51.100.1 255.255.255.0 ' + suffix)
            for command in ('ip address 192.0.2.1 255.255.255.0', 'ip address 198.51.100.1 255.255.255.0 ' + suffix):
                result = run(config, 'interface Gi0/1\n' + command, vendor)
                self.assertApplied(result)
                self.assertEqual(result['results'][-1]['status'], 'noop')
                self.assertEqual(result['config'], config)

    def test_secondary_inverse_cannot_override_replayed_address(self):
        config = fixture(interface=' ip address 192.0.2.1 255.255.255.0\n ip address 198.51.100.1 255.255.255.0 secondary\n no ip address 198.51.100.1 255.255.255.0 secondary')
        result = run(config, 'interface Gi0/1\nip address 198.51.100.1 255.255.255.0 secondary')
        self.assertApplied(result)
        self.assertEqual(result['inventory']['interfaces']['Gi0/1']['addresses'], ['192.0.2.1/24', '198.51.100.1/24'])

    def test_same_interface_address_different_mask_rejected(self):
        config = fixture(interface=' ip address 192.0.2.1 255.255.255.0')
        self.assertRejected(run(config, 'interface Gi0/1\nip address 192.0.2.1 255.255.255.128 secondary'), config)

    def test_duplicate_ipv4_same_vrf_blocked(self):
        config = fixture(interface=' ip address 192.0.2.1 255.255.255.0')
        self.assertRejected(run(config, 'interface Gi0/2\nip address 192.0.2.1 255.255.255.0'), config)

    def test_duplicate_ipv4_separate_vrf_allowed(self):
        config = fixture(interface=' ip vrf forwarding BLUE\n ip address 192.0.2.1 255.255.255.0')
        result = run(config, 'interface Gi0/2\nip address 192.0.2.1 255.255.255.0')
        self.assertApplied(result)

    def test_ipv4_invalid_host_and_masks_rejected(self):
        for address, mask in [('192.0.2.0', '255.255.255.0'), ('192.0.2.255', '255.255.255.0'), ('224.0.0.1', '255.255.255.0'), ('127.0.0.1', '255.255.255.0'), ('192.0.2.1', '0.0.0.255'), ('192.0.2.1', '24'), ('192.0.2.1', '255.0.255.0')]:
            with self.subTest(address=address, mask=mask):
                config = fixture()
                self.assertRejected(run(config, f'interface Gi0/1\nip address {address} {mask}'), config)

    def test_ipv4_on_layer2_port_blocked(self):
        config = fixture(interface=' switchport mode access')
        self.assertRejected(run(config, 'interface Gi0/1\nip address 192.0.2.1 255.255.255.0'), config)

    def test_dynamic_address_not_silently_overwritten(self):
        config = fixture(interface=' ip address dhcp')
        self.assertRejected(run(config, 'interface Gi0/1\nip address 192.0.2.1 255.255.255.0'), config)

    def test_ipv4_remove_idempotent(self):
        config = fixture(interface=' ip address 192.0.2.1 255.255.255.0')
        result = run(config, 'interface Gi0/1\nno ip address\nno ip address')
        self.assertApplied(result)
        self.assertEqual(result['results'][-1]['status'], 'noop')
        self.assertEqual(result['inventory']['interfaces']['Gi0/1']['addresses'], [])

    def test_route_inverse_cannot_override_replayed_command(self):
        route = 'ip route 198.51.100.0 255.255.255.0 192.0.2.254'
        config = fixture(extra=route + '\nno ' + route)
        result = run(config, route)
        self.assertApplied(result)
        self.assertEqual(len(result['inventory']['routes']), 1)
        self.assertNotIn('no ' + route, result['config'])

    def test_route_remove_idempotent(self):
        route = 'ip route 198.51.100.0 255.255.255.0 192.0.2.254'
        result = run(fixture(extra=route), 'no ' + route + '\nno ' + route)
        self.assertApplied(result)
        self.assertEqual(result['results'][-1]['status'], 'noop')
        self.assertEqual(result['inventory']['routes'], [])

    def test_route_invalid_values_rejected(self):
        for value in ('198.51.100.1 255.255.255.0 192.0.2.254', '198.51.100.0 24 192.0.2.254', '198.51.100.0 255.255.255.0 224.0.0.1', '198.51.100.0 255.255.255.0 192.0.2.254 999'):
            config = fixture()
            self.assertRejected(run(config, 'ip route ' + value), config)

    def test_route_cannot_use_own_interface_as_next_hop(self):
        config = fixture(interface=' ip address 192.0.2.1 255.255.255.0')
        self.assertRejected(run(config, 'ip route 0.0.0.0 0.0.0.0 192.0.2.1'), config)

    def test_acl_inverse_cannot_override_replayed_rule(self):
        config = fixture(extra='ip access-list extended LAB\n 10 permit ip any any\n no 10\n!')
        result = run(config, 'ip access-list extended LAB\n10 deny ip any any')
        self.assertApplied(result)
        self.assertEqual(result['inventory']['acls']['LAB']['rules'][0]['action'], 'deny')
        self.assertEqual(len(result['inventory']['acls']['LAB']['rules']), 1)

    def test_acl_port_protocol_and_range_validation(self):
        for rule in ('10 permit tcp any any eq 99999', '10 permit icmp any eq 22 any', '10 permit tcp any any range 900 100', '10 permit tcp any any eq www', '10 permit ip any any eq 80', '10 permit tcp any'):
            config = fixture()
            with self.subTest(rule=rule):
                self.assertRejected(run(config, 'ip access-list extended LAB\n' + rule), config)

    def test_acl_noncontiguous_wildcard_rejected(self):
        config = fixture()
        self.assertRejected(run(config, 'ip access-list extended LAB\n10 permit ip 192.0.2.0 0.0.5.255 any'), config)

    def test_nonios_acl_duplicate_fields_and_basic_destination_rejected(self):
        for vendor in ('huawei', 'h3c'):
            config = fixture(vendor)
            self.assertRejected(run(config, 'acl number 2000\nrule 10 permit destination 192.0.2.0 0.0.0.255', vendor), config)
            self.assertRejected(run(config, 'acl number 3000\nrule 10 permit ip source any source any', vendor), config)

    def test_acl_delete_idempotent(self):
        result = run(fixture(), 'ip access-list extended LAB\n10 permit ip any any\nno 10\nno 10')
        self.assertApplied(result)
        self.assertEqual(result['results'][-1]['status'], 'noop')
        self.assertEqual(result['inventory']['acls']['LAB']['rules'], [])

    def test_acl_binding_requires_populated_acl(self):
        config = fixture()
        self.assertRejected(run(config, 'interface Gi0/1\nip access-group MISSING in'), config)
        self.assertRejected(run(config, 'ip access-list extended LAB\nexit\ninterface Gi0/1\nip access-group LAB in'), config)

    def test_acl_binding_inverse_cannot_override_replayed_binding(self):
        config = fixture(interface=' ip access-group LAB in\n no ip access-group LAB in', extra='ip access-list extended LAB\n 10 permit ip any any\n!')
        result = run(config, 'interface Gi0/1\nip access-group LAB in')
        self.assertApplied(result)
        self.assertEqual(result['inventory']['interfaces']['Gi0/1']['acl_bindings'], {'in': 'LAB'})

    def test_acl_unbind_is_idempotent(self):
        config = fixture(interface=' ip access-group LAB in', extra='ip access-list extended LAB\n 10 permit ip any any\n!')
        result = run(config, 'interface Gi0/1\nno ip access-group LAB in\nno ip access-group LAB in')
        self.assertApplied(result)
        self.assertEqual(result['inventory']['interfaces']['Gi0/1']['acl_bindings'], {})
        self.assertEqual(result['results'][-1]['status'], 'noop')

    def test_existing_unknown_configuration_and_secrets_stay_exact(self):
        secret_lines = 'username admin secret 5 KEEP_SECRET\nunknown-widget unchanged\nsnmp-server community 7 KEEP_SNMP ro\n!'
        config = fixture(extra=secret_lines)
        result = run(config, 'interface Gi0/1\ndescription New\nend\nshow running-config')
        self.assertApplied(result)
        self.assertIn(secret_lines, result['config'])
        display = json.dumps({k: v for k, v in result.items() if k != 'config'})
        self.assertNotIn('KEEP_SECRET', display)
        self.assertNotIn('KEEP_SNMP', display)
        self.assertIn('[REDACTED]', display)

    def test_unsupported_secret_command_is_redacted(self):
        config = fixture()
        result = run(config, 'username admin secret 0 DO_NOT_SHOW')
        self.assertRejected(result, config)
        self.assertNotIn('DO_NOT_SHOW', json.dumps(result))

    def test_authentication_mode_secret_is_redacted(self):
        config = fixture('huawei', interface=' ospf authentication-mode md5 1 cipher HIDDEN')
        result = simulate_configuration(config, 'huawei', 'display current-configuration')
        self.assertApplied(result)
        self.assertNotIn('HIDDEN', result['results'][0]['output'])
        self.assertNotIn('HIDDEN', json.dumps(result['inventory']))
        self.assertIn('HIDDEN', result['config'])

    def test_unknown_runtime_commands_do_not_fake_results(self):
        for command in ('ping 192.0.2.1', 'show ip ospf neighbor', 'write memory', 'reload', 'show interfaces status'):
            config = fixture()
            result = simulate_configuration(config, 'cisco', command)
            self.assertRejected(result, config)
            self.assertEqual(result['results'][0]['status'], 'unsupported')

    def test_context_validation(self):
        for context in ({'mode': 'interface', 'target': 'Missing'}, {'mode': 'exec', 'target': 'Gi0/1'}, {'mode': 'not-a-mode', 'target': ''}, {'mode': 'exec'}, {'mode': 'exec', 'target': '', 'extra': True}):
            with self.subTest(context=context), self.assertRaises(ValueError):
                simulate_configuration(fixture(), 'cisco', '', context)

    def test_malformed_context_value_types_raise_value_error(self):
        for mode, target in (([], ''), ({}, ''), (0, ''), (None, ''), ('exec', []), ('exec', {}), ('exec', 0), ('exec', None)):
            with self.subTest(mode=mode, target=target), self.assertRaises(ValueError):
                simulate_configuration(fixture(), 'cisco', '', {'mode': mode, 'target': target})

    def test_command_control_characters_rejected(self):
        for char in ('\x00', '\x1b', '\x7f', '\x0b', '\x85', '\x9f', '\u2028', '\u2029'):
            with self.subTest(char=repr(char)), self.assertRaises(ValueError):
                simulate_configuration(fixture(), 'cisco', 'show ' + char + 'running-config')

    def test_hidden_separator_cannot_inject_extra_command(self):
        for separator in ('\x85', '\u2028', '\u2029'):
            with self.subTest(separator=repr(separator)), self.assertRaises(ValueError):
                run(fixture(), 'interface Gi0/1\ndescription test' + separator + 'shutdown')

    def test_config_control_characters_rejected(self):
        for char in ('\x00', '\x1b', '\x7f', '\x0b', '\x85', '\x9f', '\u2028', '\u2029'):
            with self.subTest(char=repr(char)), self.assertRaises(ValueError):
                simulate_configuration(fixture(interface=' description test' + char + 'shutdown'), 'cisco', '')

    def test_command_bytes_and_lines_rejected(self):
        for commands in ('!' * (MAX_COMMAND_BYTES + 1), '\n' * (MAX_COMMAND_LINES + 1)):
            with self.assertRaises(ValueError):
                simulate_configuration(fixture(), 'cisco', commands)

    def test_input_type_and_surrogate_rejected(self):
        for config, commands in ((None, ''), (fixture(), []), (fixture(), '\ud800'), ('hostname \ud800', '')):
            with self.assertRaises(ValueError):
                simulate_configuration(config, 'cisco', commands)

    def test_ambiguous_vendor_not_guessed(self):
        with self.assertRaises(ValueError):
            simulate_configuration('sysname ambiguous\n', 'auto')

    def test_unknown_vendor_rejected(self):
        with self.assertRaises(ValueError):
            simulate_configuration(fixture(), 'unknown')

    def test_invalid_vlan_boundaries_roll_back(self):
        for command in ('vlan 0', 'vlan 4095', 'vlan -1', 'vlan 1000000000000000'):
            config = fixture()
            self.assertRejected(run(config, command), config)

    def test_output_budget_prevents_repeated_show_amplification(self):
        config = fixture(extra='! ' + 'x' * (MAX_OUTPUT_BYTES // 2))
        result = simulate_configuration(config, 'cisco', '\n'.join(['show running-config'] * 8))
        self.assertApplied(result)
        output = '\n'.join(item['output'] for item in result['results'])
        self.assertLess(len(output.encode('utf-8')), MAX_OUTPUT_BYTES + 1024)
        self.assertIn('输出已截断', output)
        self.assertEqual(result['config'], config)

    def test_output_budget_does_not_accept_unknown_show(self):
        config = fixture(extra='! ' + 'x' * (MAX_OUTPUT_BYTES + 1))
        result = simulate_configuration(config, 'cisco', 'show running-config\nshow made-up')
        self.assertRejected(result, config)

    def test_readonly_summary_does_not_claim_live_link_or_route(self):
        result = simulate_configuration(fixture(), 'cisco', 'show ip interface brief\nshow ip route')
        self.assertApplied(result)
        self.assertIn('链路状态=未模拟', result['results'][0]['output'])
        self.assertIn('不代表活动路由表', result['results'][1]['output'])

    def test_diff_lines_are_separated(self):
        config = fixture(interface=' description Old').rstrip('\n')
        result = run(config, 'interface Gi0/1\ndescription New')
        self.assertApplied(result)
        self.assertIn('- description Old\n+ description New\n', result['diff'])

    def test_delete_after_unknown_warning_truncation_blocked(self):
        config = fixture(extra='\n'.join('unknown ' + str(i) for i in range(205)))
        self.assertRejected(run(config, 'no vlan 10'), config)

    def test_stp_only_supported_modeled_scope(self):
        config = fixture('huawei')
        self.assertRejected(run(config, 'interface Gi0/1\nstp bpdu-protection', 'huawei'), config)
        result = run(config, 'stp mode mstp\ninterface Gi0/1\nstp edged-port enable', 'huawei')
        self.assertApplied(result)
        self.assertEqual(result['inventory']['stp']['mode'], 'mstp')
        self.assertTrue(result['inventory']['interfaces']['Gi0/1']['stp_edge'])


if __name__ == '__main__':
    unittest.main()
