import os
import unittest
from unittest.mock import patch
from shortforge.media import youtube_command

class TermuxTests(unittest.TestCase):
    def test_desktop_command_unchanged(self):
        with patch.dict(os.environ, {'SHORTFORGE_TERMUX':'0'}):
            self.assertNotIn('--js-runtimes', youtube_command())

    def test_termux_enables_local_node(self):
        with patch.dict(os.environ, {'SHORTFORGE_TERMUX':'1'}):
            self.assertEqual(youtube_command()[-2:], ['--js-runtimes','node'])
