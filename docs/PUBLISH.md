# Public Publishing Notes

This public folder is intentionally smaller than the private working tree.

Publish this folder to GitHub when these checks pass:

```bash
python3 tools/publish_check.py
python3 -m pytest -q
```

Before pushing, confirm that the repository does not contain:

- `data/*.log`
- `data/*.jsonl`
- `data/console_state.json`
- `data/leases/`
- private robot instances under `install/robots/`
- physical robot adapters
- measured safety/current/temperature values
- customer or commercial collaboration documents

The public version is for simulation, architecture review, and integration discussion.
Validated hardware adapters and operational parameters are maintained separately.


## Release: Windows installer and update list

Every release ships three files. Installed copies trust a release only through them.

```bash
python3 tools/build_windows_installer.py          # build/windows/HangeulRobot-Setup-<VERSION>.exe (WSL + Inno Setup 6)
python3 tools/release.py sign [--safety-change] [--notes-ko "한 줄 요약"]
GITHUB_TOKEN=... python3 tools/release.py upload  # or drag the three files from build/release/v<VERSION>/
                                                  # into a new GitHub release tagged v<VERSION>
```

- `latest.json` (+ `.sig`) lists the version, installer URL, size, SHA-256, whether safety behaviour
  changes, and the CHANGELOG section. Consoles read the **latest** release's `latest.json`, so publish
  the three files together, after pushing `main`.
- Pass `--safety-change` when the minor version goes up because safety behaviour changed; the screen
  marks such a release in red.
- The signing key lives outside the repository (`~/.config/hangeul-robot/release_ed25519.pem`).
  **Back it up.** Without it, installed copies cannot be updated; a new key needs a manual reinstall,
  because the public key is inside the console (`console/src/hangeul_console/updater.py`).
- Keep older releases. Rollback downloads the release of the version currently installed
  (`releases/download/v<VERSION>/latest.json`).
