import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { App } from "../App";
import { activeVoiceLanguages, VOICE_LANGUAGES } from "./languages";

/** A stand-in for the browser's SpeechRecognition, driven by the test. */
class FakeRecognition {
  static instances: FakeRecognition[] = [];
  lang = "";
  interimResults = false;
  continuous = true;
  maxAlternatives = 0;
  started = false;
  onresult: ((e: unknown) => void) | null = null;
  onerror: ((e: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  constructor() {
    FakeRecognition.instances.push(this);
  }
  start() {
    this.started = true;
  }
  stop() {
    this.started = false;
    this.onend?.();
  }
  abort() {
    this.stop();
  }
  /** Simulate speech: a list of [transcript, isFinal] results. */
  say(results: [string, boolean][]) {
    const list = results.map(([t, isFinal]) => Object.assign([{ transcript: t, confidence: 0.9 }], { isFinal }));
    act(() => this.onresult?.({ resultIndex: 0, results: list }));
  }
  fail(error: string) {
    act(() => {
      this.onerror?.({ error });
      this.onend?.();
    });
  }
  end() {
    act(() => this.onend?.());
  }
}

const last = () => FakeRecognition.instances.at(-1)!;

beforeEach(() => {
  FakeRecognition.instances = [];
});
afterEach(() => {
  delete (window as unknown as Record<string, unknown>).SpeechRecognition;
  delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
});

function withVoice(name: "SpeechRecognition" | "webkitSpeechRecognition" = "webkitSpeechRecognition") {
  (window as unknown as Record<string, unknown>)[name] = FakeRecognition;
}

async function home() {
  window.history.replaceState(null, "", "/?store=central");
  const user = userEvent.setup();
  const calls = { search: 0 };
  render(<App />);
  await screen.findByRole("combobox", { name: "Store" });
  return { user, calls };
}

describe("language list", () => {
  it("is ready for Hindi and Tamil, but only English is switched on, en-IN first", () => {
    expect(VOICE_LANGUAGES.map((l) => l.code)).toEqual(expect.arrayContaining(["en-IN", "en-US", "hi-IN", "ta-IN"]));
    expect(activeVoiceLanguages().map((l) => l.code)).toEqual(["en-IN", "en-US"]);
  });
});

it("hides the mic when the browser has no speech recognition", async () => {
  await home();
  expect(screen.queryByRole("button", { name: /voice/i })).not.toBeInTheDocument();
});

it("works with the unprefixed SpeechRecognition too", async () => {
  withVoice("SpeechRecognition");
  await home();
  expect(screen.getByRole("button", { name: "Search by voice" })).toBeInTheDocument();
});

it("listens in en-IN, shows the words as they come, and puts the transcript in the bar without searching", async () => {
  withVoice();
  const { user } = await home();
  await user.click(screen.getByRole("button", { name: "Search by voice" }));
  expect(last().lang).toBe("en-IN");
  expect(last().started).toBe(true);
  expect(screen.getByRole("button", { name: "Stop listening" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("status")).toHaveTextContent("Listening…");

  last().say([["milk and", false]]);
  expect(screen.getByRole("combobox", { name: "Search products" })).toHaveValue("milk and");
  last().say([["milk and bread", true]]);
  last().end();

  expect(screen.getByRole("combobox", { name: "Search products" })).toHaveValue("milk and bread");
  expect(screen.getByRole("combobox", { name: "Search products" })).toHaveFocus();
  expect(screen.getByRole("status")).toHaveTextContent("Check the words, then tap Search.");
  expect(screen.getByRole("button", { name: "Search by voice" })).toHaveAttribute("aria-pressed", "false");
  expect(screen.queryByRole("heading", { name: /Results for/ })).not.toBeInTheDocument();
});

it("tapping the mic again stops listening", async () => {
  withVoice();
  const { user } = await home();
  await user.click(screen.getByRole("button", { name: "Search by voice" }));
  await user.click(screen.getByRole("button", { name: "Stop listening" }));
  expect(last().started).toBe(false);
  expect(screen.getByRole("button", { name: "Search by voice" })).toBeInTheDocument();
});

it("falls back to en-US once if en-IN is not supported", async () => {
  withVoice();
  const { user } = await home();
  await user.click(screen.getByRole("button", { name: "Search by voice" }));
  last().fail("language-not-supported");
  expect(FakeRecognition.instances).toHaveLength(2);
  expect(last().lang).toBe("en-US");
  last().fail("language-not-supported");
  expect(FakeRecognition.instances).toHaveLength(2);
  expect(screen.getByRole("status")).toHaveTextContent("Voice search isn't available in this browser");
});

it("explains a denied microphone in plain words", async () => {
  withVoice();
  const { user } = await home();
  await user.click(screen.getByRole("button", { name: "Search by voice" }));
  last().fail("not-allowed");
  expect(screen.getByRole("status")).toHaveTextContent("Microphone access is off. Allow it in your browser settings, or type instead.");
  expect(screen.getByRole("button", { name: "Search by voice" })).toBeInTheDocument();
});

it("says so when it heard nothing, and keeps what was typed", async () => {
  withVoice();
  const { user } = await home();
  await user.type(screen.getByRole("combobox", { name: "Search products" }), "eggs");
  await user.click(screen.getByRole("button", { name: "Search by voice" }));
  last().fail("no-speech");
  expect(screen.getByRole("status")).toHaveTextContent("We didn't hear anything. Try again.");
  expect(screen.getByRole("combobox", { name: "Search products" })).toHaveValue("eggs");
});

it("has no accessibility violations while listening", async () => {
  withVoice();
  const { user } = await home();
  await user.click(screen.getByRole("button", { name: "Search by voice" }));
  expect(await axe(document.body)).toHaveNoViolations();
});
