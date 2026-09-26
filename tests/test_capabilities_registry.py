"""Unit tests for Jarvis Capabilities & Knowledge Registry.

Tests dynamic schema synchronization, identity and capability queries,
domain drill-downs, System 1 reflex dispatcher routing, and System 2 prompt grounding.
"""

import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

import yaml
from core.capabilities import JarvisCapabilitiesRegistry, capabilities_registry
from core.dispatcher import CommandDispatcher
from core.system2_agent import System2Agent


class TestCapabilitiesRegistry(unittest.TestCase):
    """Test suite for the central JarvisCapabilitiesRegistry."""

    def setUp(self):
        self.registry = capabilities_registry

    def test_schema_loading_and_counts(self):
        """Verify schema.yaml is dynamically parsed with all intents and templates."""
        self.assertGreaterEqual(self.registry.total_intents, 14)
        self.assertGreaterEqual(self.registry.total_templates, 200)
        self.assertIn("JARVIS_IDENTITY", self.registry.intents)
        self.assertIn("JARVIS_CAPABILITIES", self.registry.intents)
        self.assertIn("AUDIO_CONTROL", self.registry.intents)
        self.assertIn("DEVICE_CONTROL", self.registry.intents)
        self.assertIn("SYSTEM_ACTION", self.registry.intents)

    def test_get_identity(self):
        """Verify canonical persona and system identity."""
        ident = self.registry.get_identity()
        self.assertEqual(ident["name"], "Jarvis")
        self.assertIn("Omarchy", ident["role"])
        self.assertIn("Hyprland", ident["system"])
        self.assertIn("System 1", ident["tier1"])
        self.assertIn("System 2", ident["tier2"])
        self.assertIn("Kokoro-82M", ident["voice"])
        self.assertIn("Arc-Reactor", ident["ui"])
        self.assertIn("I am Jarvis", ident["speech"])
        self.assertGreater(len(ident["speech"]), 20)

    def test_get_overview(self):
        """Verify capability overview across all core functional domains."""
        overview = self.registry.get_overview()
        domains = overview["domains"]
        expected_domains = [
            "windows",
            "apps",
            "audio",
            "hardware",
            "system",
            "vision",
            "awareness",
            "chaining",
            "reasoning",
        ]
        for d in expected_domains:
            self.assertIn(d, domains)

        self.assertEqual(overview["total_domains"], len(expected_domains))
        self.assertIn("I can manage your Hyprland windows", overview["speech"])

    def test_resolve_domain(self):
        """Verify fuzzy and alias resolution to canonical domains."""
        self.assertEqual(self.registry.resolve_domain("windows"), "windows")
        self.assertEqual(self.registry.resolve_domain("workspace"), "windows")
        self.assertEqual(self.registry.resolve_domain("audio"), "audio")
        self.assertEqual(self.registry.resolve_domain("sound"), "audio")
        self.assertEqual(self.registry.resolve_domain("microphone"), "audio")
        self.assertEqual(self.registry.resolve_domain("wifi"), "hardware")
        self.assertEqual(self.registry.resolve_domain("bluetooth"), "hardware")
        self.assertEqual(self.registry.resolve_domain("brightness"), "hardware")
        self.assertEqual(self.registry.resolve_domain("telemetry"), "system")
        self.assertEqual(self.registry.resolve_domain("cpu"), "system")
        self.assertEqual(self.registry.resolve_domain("screen"), "vision")
        self.assertEqual(self.registry.resolve_domain("sentinel"), "awareness")
        self.assertEqual(self.registry.resolve_domain("compound"), "chaining")
        self.assertEqual(self.registry.resolve_domain("gemini"), "reasoning")
        self.assertIsNone(self.registry.resolve_domain("completely_unrelated_query_12345"))

    def test_get_domain_details(self):
        """Verify domain drill-down provides templates, actions, slots, and spoken voice."""
        audio_details = self.registry.get_domain_details("audio")
        self.assertIsNotNone(audio_details)
        self.assertEqual(audio_details["domain"], "audio")
        self.assertIn("MEDIA_CONTROL", audio_details["schema_intents"])
        self.assertIn("AUDIO_CONTROL", audio_details["schema_intents"])
        self.assertGreater(audio_details["total_templates"], 0)
        self.assertIn("play", audio_details["registered_actions"])
        self.assertIn("pause", audio_details["registered_actions"])
        self.assertIn("sink", audio_details["slots"])
        self.assertIn("For audio", audio_details["speech"])

    def test_cli_formatters(self):
        """Verify CLI matrix and domain drill-down formatters."""
        cli_overview = self.registry.format_cli_overview()
        self.assertIn("OMARCHY JARVIS CAPABILITIES MATRIX", cli_overview)
        self.assertIn("windows", cli_overview)
        self.assertIn("audio", cli_overview)
        self.assertIn("hardware", cli_overview)

        cli_domain = self.registry.format_cli_domain("wifi")
        self.assertIn("JARVIS CAPABILITY: HARDWARE, NETWORK & DISPLAY CONTROL", cli_domain)
        self.assertIn("nmcli", cli_domain)
        self.assertIn("Voice Command Examples:", cli_domain)

    def test_system_prompt_context(self):
        """Verify prompt context contains all domain definitions and examples."""
        context = self.registry.format_system_prompt_context()
        self.assertIn("Jarvis Built-In OS Capabilities", context)
        self.assertIn("Hyprland Windows & Workspaces", context)
        self.assertIn("Media Playback & Audio Device Routing", context)
        self.assertIn("Hardware, Network & Display Control", context)
        self.assertIn("Visual Perception & Screen Grounding", context)
        self.assertIn("registered intent categories", context)

    def test_dynamic_reload(self):
        """Verify registry automatically reloads when schema file is modified."""
        sample_schema = {
            "intents": {
                "TEST_INTENT_A": {
                    "description": "Test Intent A",
                    "templates": ["test template one", "test template two"],
                }
            }
        }
        with tempfile.NamedTemporaryFile("w+", suffix=".yaml", delete=False) as tf:
            yaml.safe_dump(sample_schema, tf)
            temp_path = tf.name

        try:
            reg = JarvisCapabilitiesRegistry(schema_path=temp_path)
            self.assertEqual(reg.total_intents, 1)
            self.assertEqual(reg.total_templates, 2)

            # Update file
            time.sleep(0.05)
            sample_schema["intents"]["TEST_INTENT_B"] = {
                "description": "Test Intent B",
                "templates": ["test template three"],
            }
            with open(temp_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(sample_schema, f)

            # Registry should detect change on next property access
            self.assertEqual(reg.total_intents, 2)
            self.assertEqual(reg.total_templates, 3)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestDispatcherCapabilitiesIntegration(unittest.TestCase):
    """Test suite for CommandDispatcher reflex handling of identity and capability commands."""

    def setUp(self):
        self.disp = CommandDispatcher()

    def test_identity_queries(self):
        """Verify identity queries match JARVIS_IDENTITY in sub-30ms."""
        queries = [
            "who are you",
            "what are you",
            "identify yourself",
            "tell me about yourself",
            "who made you",
            "what is jarvis",
            "introduce yourself",
        ]
        for q in queries:
            res = self.disp.dispatch_text(q, execute=False)
            self.assertTrue(res["matched"], f"Failed to match identity for '{q}'")
            self.assertEqual(res["intent"], "JARVIS_IDENTITY")
            self.assertEqual(res["action"], "identify_jarvis")

    def test_overview_queries(self):
        """Verify general capabilities queries match JARVIS_CAPABILITIES in sub-30ms."""
        queries = [
            "what can you do",
            "what are you capable of",
            "what are your capabilities",
            "list capabilities",
            "show capabilities",
            "what features do you have",
            "what commands do you support",
            "what commands can i run",
            "help",
            "help me",
        ]
        for q in queries:
            res = self.disp.dispatch_text(q, execute=False)
            self.assertTrue(res["matched"], f"Failed to match overview for '{q}'")
            self.assertEqual(res["intent"], "JARVIS_CAPABILITIES")
            self.assertEqual(res["action"], "capabilities_overview")

    def test_domain_queries(self):
        """Verify domain drill-down queries match JARVIS_CAPABILITIES with specific action."""
        cases = [
            ("what can you do with audio", "capabilities_domain_audio"),
            ("tell me about windows", "capabilities_domain_windows"),
            ("tell me about wifi", "capabilities_domain_hardware"),
            ("vision capabilities", "capabilities_domain_vision"),
            ("system capabilities", "capabilities_domain_system"),
            ("how does awareness work", "capabilities_domain_awareness"),
            ("what are your capabilities with apps", "capabilities_domain_apps"),
        ]
        for q, expected_action in cases:
            res = self.disp.dispatch_text(q, execute=False)
            self.assertTrue(res["matched"], f"Failed to match domain query '{q}'")
            self.assertEqual(res["intent"], "JARVIS_CAPABILITIES")
            self.assertEqual(res["action"], expected_action)

    def test_execution_with_speech_generation(self):
        """Verify live execution produces spoken response without LLM delay."""
        res = self.disp.dispatch_text("who are you", execute=True)
        self.assertTrue(res["matched"])
        self.assertTrue(res["success"])
        self.assertIn("speech", res)
        self.assertIn("I am Jarvis", res["speech"])
        self.assertLess(res["latency_ms"], 30.0)

        res_dom = self.disp.dispatch_text("what can you do with audio", execute=True)
        self.assertTrue(res_dom["matched"])
        self.assertTrue(res_dom["success"])
        self.assertIn("speech", res_dom)
        self.assertIn("For audio", res_dom["speech"])
        self.assertLess(res_dom["latency_ms"], 30.0)


class TestSystem2AgentCapabilitiesGrounding(unittest.TestCase):
    """Test suite for System2Agent prompt grounding with live capability registry."""

    def test_format_system_prompt_includes_capabilities(self):
        agent = System2Agent(enable_tts=False)
        telemetry = {
            "active_window": {"title": "Terminal", "class": "ghostty", "workspace": 1},
            "open_windows": [{"title": "Terminal", "class": "ghostty"}],
        }
        prompt = agent.format_system_prompt(telemetry)
        self.assertIn("Jarvis Built-In OS Capabilities", prompt)
        self.assertIn("Hyprland Windows & Workspaces", prompt)
        self.assertIn("Media Playback & Audio Device Routing", prompt)


if __name__ == "__main__":
    unittest.main()
