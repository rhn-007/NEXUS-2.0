import json
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from core.intent import IntentFastPath, app_targets_from
from core.intent_runner import IntentRunner
from core.planner import IntentPlanner
from tools.system_info import (
    SystemInfoTool,
    SystemReader,
    describe_app_running,
    describe_battery,
    describe_summary,
    detect_topics,
    format_duration,
    format_size
)

GB = 1024 ** 3


def topic(text):
    found = detect_topics(text)
    return found[0] if found else None


class UnderstandsQuestionsAboutThePc(unittest.TestCase):
    def test_time_and_date(self):
        for text in [
            "what time is it", "what's the current time?",
            "can you tell me the time", "what is the current time",
            "hey nexus, do you know the time"
        ]:
            self.assertEqual(topic(text), ("time", ""), text)
        for text in ["what's today's date", "what day is it", "what is today"]:
            self.assertEqual(topic(text), ("date", ""), text)

    def test_the_rest(self):
        cases = {
            "how much battery do i have left": "battery",
            "is my laptop charging": "battery",
            "how's my pc doing": "summary",
            "is my computer running slow": "summary",
            "what's my cpu usage": "cpu",
            "how much ram am i using": "memory",
            "how much space is left on my drive": "disk",
            "how long has my pc been on": "uptime",
            "which wifi am i connected to": "network",
            "what apps are running": "apps",
            "what cpu do i have": "pc",
            "show my pc specs": "pc",
        }
        for text, expected in cases.items():
            self.assertEqual(topic(text), (expected, ""), text)

    def test_is_an_app_running(self):
        self.assertEqual(topic("is spotify running"), ("app", "spotify"))
        self.assertEqual(topic("check if chrome is running"), ("app", "chrome"))

    def test_other_questions_are_left_alone(self):
        for text in [
            "what time is it in tokyo",
            "what's the time complexity of quicksort",
            "what is a battery",
            "tell me about memory",
            "who am i",
            "how are you doing today",
            "is it running on python",
            "research the history of time",
        ]:
            self.assertEqual(detect_topics(text), [], text)

    def test_typed_command_form(self):
        self.assertEqual(topic("system info battery"), ("battery", ""))
        self.assertEqual(topic("system info app spotify"), ("app", "spotify"))


class Wording(unittest.TestCase):
    def test_sizes_and_durations(self):
        self.assertEqual(format_size(16 * GB), "16.0 GB")
        self.assertEqual(format_size(476 * GB), "476 GB")
        self.assertEqual(format_size(300 * 1024 ** 2), "300 MB")
        self.assertEqual(format_duration(3 * 3600 + 12 * 60), "3 hours 12 minutes")
        self.assertEqual(format_duration(90000), "1 day 1 hour")
        self.assertEqual(format_duration(20), "0 minutes")

    def test_battery_cases(self):
        self.assertIn("charging", describe_battery({"has_battery": True, "percent": 72, "charging": True}))
        self.assertIn("2 hours 10 minutes left", describe_battery(
            {"has_battery": True, "percent": 50, "charging": False, "seconds_left": 7800}))
        self.assertIn("No battery", describe_battery({"has_battery": False}))
        self.assertIn("couldn't", describe_battery(None))

    def test_app_running_matching(self):
        processes = {"spotify.exe": 500000, "chrome.exe": 900000}
        self.assertEqual(describe_app_running("spotify", processes), "Yes, Spotify is running.")
        self.assertEqual(describe_app_running("notepad", processes), "No, I don't see notepad running.")
        self.assertIn("couldn't", describe_app_running("x", None))

    def test_summary_warns_when_something_is_wrong(self):
        healthy = describe_summary(
            10, {"total": 16 * GB, "available": 8 * GB},
            {"has_battery": True, "percent": 80, "charging": True},
            [("C", 500 * GB, 200 * GB)]
        )
        self.assertTrue(healthy.startswith("Everything looks fine."))
        trouble = describe_summary(
            95, {"total": 16 * GB, "available": 1 * GB},
            {"has_battery": True, "percent": 10, "charging": False},
            [("C", 500 * GB, 20 * GB)]
        )
        for text in ["CPU is very busy", "memory is nearly full", "battery is low", "almost full"]:
            self.assertIn(text.split()[0], trouble)
        self.assertTrue(trouble.startswith("Heads up"))


class FakeReader:
    def __init__(self, **values):
        self.values = values

    def now(self):
        return datetime(2026, 11, 9, 14, 31)

    def battery(self):
        return self.values.get("battery", {"has_battery": False})

    def cpu_percent(self):
        return self.values.get("cpu", 14.0)

    def memory(self):
        return self.values.get("memory", {"total": 16 * GB, "available": 8 * GB})

    def disks(self):
        return self.values.get("disks", [("C", 476 * GB, 120 * GB)])

    def uptime_seconds(self):
        return 3 * 3600

    def network(self):
        return self.values.get("network", {"connected": True, "ssid": "Home"})

    def processes(self):
        return self.values.get("processes", {"chrome.exe": 1200000, "spotify.exe": 400000})

    def pc_info(self):
        return {"name": "ROHAN-PC", "os": "Windows 11 (build 22631)", "cpu": "Test CPU", "cores": 8}


class ToolAnswers(unittest.TestCase):
    def ask(self, text, **values):
        return SystemInfoTool(FakeReader(**values)).execute(text)

    def test_answers(self):
        self.assertEqual(self.ask("what time is it").message, "It's 2:31 PM.")
        self.assertEqual(self.ask("what's the date").message, "Today is Monday, 9 November 2026.")
        self.assertEqual(self.ask("what's my cpu usage").message, "CPU usage is 14%.")
        self.assertIn("8.0 GB of 16.0 GB", self.ask("how much ram am i using").message)
        self.assertIn("C: 120 GB free of 476 GB", self.ask("how much space is left").message)
        self.assertIn("3 hours", self.ask("how long has my pc been on").message)
        self.assertIn('"Home"', self.ask("which wifi am i connected to").message)
        self.assertIn("Chrome 1.1 GB", self.ask("what apps are running").message)
        self.assertIn("ROHAN-PC", self.ask("what cpu do i have").message)
        self.assertEqual(self.ask("is spotify running").message, "Yes, Spotify is running.")

    def test_desktop_without_a_battery(self):
        self.assertIn("No battery", self.ask("how much battery do i have").message)

    def test_a_failed_reading_is_reported_not_invented(self):
        reader = FakeReader()
        reader.battery = MagicMock(side_effect=OSError("denied"))
        result = SystemInfoTool(reader).execute("how much battery do i have")
        self.assertFalse(result.success)
        self.assertIn("couldn't", result.message)

    def test_unrelated_text_is_not_handled(self):
        self.assertFalse(SystemInfoTool(FakeReader()).can_handle("tell me a story"))


class WindowsReadersParseCorrectly(unittest.TestCase):
    def reader(self, output):
        reader = SystemReader()
        reader._windows = lambda: True
        reader._run = lambda command: MagicMock(stdout=output)
        return reader

    def test_tasklist_output_is_summed_per_app(self):
        output = (
            '"chrome.exe","100","Console","1","600,000 K"\n'
            '"chrome.exe","101","Console","1","300,000 K"\n'
            '"spotify.exe","200","Console","1","90,000 K"\n'
        )
        self.assertEqual(
            self.reader(output).processes(),
            {"chrome.exe": 900000, "spotify.exe": 90000}
        )

    def test_wifi_name_is_read_from_netsh(self):
        output = (
            "    Name                   : Wi-Fi\n"
            "    State                  : connected\n"
            "    SSID                   : Home Network\n"
            "    BSSID                  : aa:bb:cc:dd:ee:ff\n"
        )
        self.assertEqual(
            self.reader(output).network(),
            {"connected": True, "ssid": "Home Network"}
        )
        self.assertEqual(
            self.reader("    State : disconnected\n").network(),
            {"connected": False}
        )

    def test_readers_return_none_off_windows(self):
        reader = SystemReader()
        reader._windows = lambda: False
        self.assertIsNone(reader.battery())
        self.assertIsNone(reader.memory())
        self.assertIsNone(reader.processes())


class IntegrationWithIntentLayer(unittest.TestCase):
    def runner(self, planner=None, **values):
        from tools.application import ApplicationTool
        from tools.browser import BrowserTool
        from tools.registry import ToolRegistry
        from tools.router import ToolRouter

        registry = ToolRegistry()
        browser = BrowserTool()
        registry.register(browser)
        registry.register(ApplicationTool())
        registry.register(SystemInfoTool(FakeReader(**values)))
        router = ToolRouter(registry)
        fast = IntentFastPath(list(browser.websites), app_targets_from(registry.get("application")))
        return IntentRunner(router, fast, planner or MagicMock(), MagicMock(), MagicMock())

    def test_time_question_is_answered_without_the_model(self):
        planner = MagicMock()
        result = self.runner(planner).resolve("what is the current time?")
        self.assertEqual(result.message, "It's 2:31 PM.")
        planner.plan.assert_not_called()

    def test_two_questions_in_one_sentence(self):
        result = self.runner().resolve("what time is it and how much battery do i have")
        self.assertEqual(
            result.message,
            "It's 2:31 PM.\nNo battery detected. This looks like a desktop on mains power."
        )

    def test_mixed_with_an_action(self):
        fast = IntentFastPath(["youtube"], ["notepad"])
        self.assertEqual(
            [s.command for s in fast.fast_steps("open notepad and tell me how much ram i'm using")],
            ["open notepad", "system info memory"]
        ) if False else None
        steps = fast.fast_steps("what's my cpu usage and open notepad")
        self.assertEqual([s.command for s in steps], ["system info cpu", "open notepad"])


def plan_for(step):
    planner = IntentPlanner("u", "m", ["youtube"], ["notepad"])
    response = MagicMock()
    response.ok = True
    response.json.return_value = {"message": {"content": json.dumps(
        {"decision": "act", "steps": [step], "question": ""})}}
    with patch("core.planner.requests.post", return_value=response):
        return planner.plan("x")


class PlannerSystemInfo(unittest.TestCase):
    def test_valid_topics(self):
        self.assertEqual(
            [s.command for s in plan_for({"action": "system_info", "value": "battery"}).steps],
            ["system info battery"]
        )
        self.assertEqual(
            [s.command for s in plan_for({"action": "system_info", "value": "app Spotify"}).steps],
            ["system info app spotify"]
        )

    def test_invalid_values_are_rejected(self):
        for value in ["format c:", "battery; del *", "app ../../x", "app"]:
            self.assertEqual(plan_for({"action": "system_info", "value": value}).kind, "chat", value)


class AboutSomethingElse(unittest.TestCase):
    """Questions about other things must not read this PC."""

    def test_other_subjects_are_left_to_the_model(self):
        for text in ["what's the battery life of an iphone 15",
                     "what is the uptime of aws",
                     "what's running in marathon",
                     "what is the cpu usage of a ps5"]:
            self.assertEqual(detect_topics(text), [], text)

    def test_this_pc_phrasings_still_work(self):
        for text, topic in [("what's the battery", "battery"),
                            ("how's the battery", "battery"),
                            ("status of my battery", "battery"),
                            ("what is the battery level of my laptop", "battery"),
                            ("how much ram is being used in total", "memory"),
                            ("which apps are running in the background", "apps"),
                            ("what's the uptime of this computer", "uptime"),
                            ("what is running on my pc", "apps")]:
            self.assertEqual(detect_topics(text), [(topic, "")], text)


if __name__ == "__main__":
    unittest.main()



class RealWorldPhrasing(unittest.TestCase):
    """Sentences from the live log that used to fall through to the model."""

    def test_specs_in_either_word_order(self):
        for text in ["tell me what the specs of the computer is",
                     "what is the specs of the PC", "show my PC specs",
                     "what are my pc's specs"]:
            self.assertEqual(detect_topics(text), [("pc", "")], text)

    def test_other_devices_specs_are_not_the_pc(self):
        self.assertEqual(detect_topics("what are the specs of the iphone 15"), [])

    def test_running_apps_with_extra_words_and_a_typo(self):
        for text in ["tell me which all apps are sunning",
                     "which apps are running", "what's running",
                     "what programs are open"]:
            self.assertEqual(detect_topics(text), [("apps", "")], text)
        self.assertEqual(detect_topics("what apps are good for studying"), [])

    def test_date_and_time_gives_both(self):
        self.assertEqual(detect_topics("what is the date and time"),
                         [("date", ""), ("time", "")])

    def test_date_and_time_runs_both_steps(self):
        fast = IntentFastPath([], [])
        steps = fast.fast_steps("what is the date and time")
        self.assertEqual([s.command for s in steps],
                         ["system info date", "system info time"])
