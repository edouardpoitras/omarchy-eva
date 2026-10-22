# Contributing to Omarchy Eva

Thank you for your interest in contributing to **Omarchy Eva**!

Eva is designed as a real-time, voice-driven reflex and task execution engine for Omarchy Linux and the Hyprland Wayland compositor.

---

## Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/<your-username>/omarchy-eva.git
   cd omarchy-eva
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements-dev.txt
   ```

3. **Install the package in editable mode:**
   ```bash
   pip install -e .
   ```

---

## Running Tests

Eva maintains a suite of fast, self-contained unit tests:

```bash
# Run all unit tests
python3 -m unittest discover -s tests -p 'test_*.py'

# Or using pytest (if installed)
pytest tests/
```

Before submitting a PR, ensure that all tests pass without errors.

---

## Code Style & Architecture Guidelines

* **Sub-150ms Reflex Tier (System 1):** Fast desktop interactions (moving windows, switching workspaces, volume, media playback, quick queries) should never block on network requests or heavy models. Keep System 1 reflex execution instantaneous.
* **Deterministic Fallback First:** When adding domain models or routing logic, always provide a deterministic, zero-latency local fallback.
* **Preserve Documentation:** Keep existing docstrings and typing annotations consistent.
* **Privacy by Default:** Do not commit personal machine paths, credentials, tokens, or personal screen captures. Runtime artifacts (`assets/captures/`, `.cache/`, `/dev/shm/`) must remain gitignored.

---

## Submitting Pull Requests

1. Fork the repository and create your feature branch:
   ```bash
   git checkout -b feature/my-new-feature
   ```
2. Commit your changes with descriptive commit messages.
3. Verify that all tests pass:
   ```bash
   python3 -m unittest discover -s tests -p 'test_*.py'
   ```
4. Push to your fork and submit a Pull Request against `main`.

---

## License

By contributing to Omarchy Eva, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).
