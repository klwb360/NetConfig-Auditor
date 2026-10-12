import unittest
from netaudit.simulator import simulate_configuration

class PartialRouteDisplayTests(unittest.TestCase):
    def test_show_marks_unmodeled_route_parameters(self):
        backup = 'hostname X\nip route 10.0.0.0 255.255.255.0 192.0.2.1 track 10\n'
        result = simulate_configuration(backup, 'cisco', 'show ip route')
        self.assertEqual(result['config'], backup)
        self.assertIn('参数未完整建模', result['results'][0]['output'])

if __name__ == '__main__':
    unittest.main()
