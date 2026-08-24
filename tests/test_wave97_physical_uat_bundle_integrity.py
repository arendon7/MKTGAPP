from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRITER = ROOT / "scripts/write_physical_uat_candidate.py"
VERIFIER = ROOT / "scripts/verify_physical_uat_handoff.py"
FINALIZER = ROOT / "scripts/finalize_physical_uat.py"
RECORD = ROOT / "scripts/record_release_uat.command"
FINALIZE_COMMAND = ROOT / "scripts/finalize_physical_uat.command"
VERSION = ROOT / "src/binario_marketing/version.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave97PhysicalUATBundleIntegrityTests(unittest.TestCase):
    def test_writer_verifier_and_finalizer_use_identical_source_digest_algorithm(self):
        writer = _load(WRITER, "w97_writer")
        verifier = _load(VERIFIER, "w97_verifier")
        finalizer = _load(FINALIZER, "w97_finalizer")
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw) / "source"
            for root in (source / "src", source / "web", source / "apps"):
                root.mkdir(parents=True)
            (source / "src/a.py").write_text("print('a')\n", encoding="utf-8")
            (source / "web/b.js").write_text("console.log('b')\n", encoding="utf-8")
            (source / "apps/c.json").write_text('{"c":1}\n', encoding="utf-8")
            expected = writer._source_digest(source)
            self.assertEqual(verifier._source_digest(source), expected)
            self.assertEqual(finalizer._source_digest(source), expected)
            (source / "web/b.js").write_text("tampered\n", encoding="utf-8")
            changed = writer._source_digest(source)
            self.assertNotEqual(changed, expected)
            self.assertEqual(verifier._source_digest(source), changed)
            self.assertEqual(finalizer._source_digest(source), changed)

    def test_record_gate_revalidates_codesign_before_handoff_and_mutation(self):
        subprocess.run(["bash", "-n", str(RECORD)], check=True)
        source = RECORD.read_text(encoding="utf-8")
        codesign = source.index('codesign --verify --deep --strict "$APP"')
        handoff = source.index('"$VERIFY" --delivery-dir', codesign)
        mutation = source.index('"$RECORDER"', handoff)
        self.assertLess(codesign, handoff)
        self.assertLess(handoff, mutation)
        self.assertIn("candidate bundle signature drift detected", source)
        self.assertIn("--require-physical-host", source)

    def test_finalization_revalidates_codesign_and_handoff_immediately_before_seal(self):
        subprocess.run(["bash", "-n", str(FINALIZE_COMMAND)], check=True)
        source = FINALIZE_COMMAND.read_text(encoding="utf-8")
        codesign = source.index('codesign --verify --deep --strict "$APP"')
        handoff = source.index('"$VERIFY" --delivery-dir', codesign)
        finalizer = source.index('"$FINALIZER"', handoff)
        self.assertLess(codesign, handoff)
        self.assertLess(handoff, finalizer)
        self.assertIn("PHYSICAL_UAT_HANDOFF_VERIFICATION.json", source)
        self.assertIn("--require-physical-host", source)

    def test_integrity_hardening_does_not_mutate_release_contract_or_workflow_count(self):
        version = VERSION.read_text(encoding="utf-8")
        self.assertIn('__version__ = "0.9.0"', version)
        self.assertIn("RELEASE_READY = True", version)
        self.assertIn('RELEASE_TAG: str | None = "v0.9.0"', version)
        workflows = sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        verifier = VERIFIER.read_text(encoding="utf-8")
        finalizer = FINALIZER.read_text(encoding="utf-8")
        self.assertIn("candidate source digest does not match extracted app", verifier)
        self.assertIn("candidate source digest does not match extracted app", finalizer)
        for source in (verifier, finalizer):
            self.assertNotIn("gh release create", source)
            self.assertNotIn("RELEASE_READY = True", source)


if __name__ == "__main__":
    unittest.main()
