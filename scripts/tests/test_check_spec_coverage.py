import check_spec_coverage
import pytest

IMPLEMENTED = """# 0001 — X

- **Status:** Implemented

## Acceptance criteria

- **ENG-X-001**: behaviour.
"""


@pytest.mark.spec("DEV-SDD-012")
def test_implemented_specs_need_a_verification_record(tmp_path, monkeypatch, capsys) -> None:
    spec = tmp_path / "specs" / "0001-x" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(IMPLEMENTED)
    tests = tmp_path / "packages" / "engine" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_x.py").write_text('@pytest.mark.spec("ENG-X-001")')
    monkeypatch.setattr(check_spec_coverage, "ROOT", tmp_path)

    assert check_spec_coverage.main() == 1
    assert "Verification" in capsys.readouterr().out

    spec.write_text(IMPLEMENTED + "\n## Verification\n\n- recorded\n")
    assert check_spec_coverage.main() == 0
