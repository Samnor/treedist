"""--utvecklare adds output for following a number to its source; without it a month is its appendices and little else."""

from pathlib import Path

import pandas as pd
import pytest

from treedist.cli import main

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"
PERIOD = "2026-01"


def run(tmp_path, name, *extra):
    out = tmp_path / name / "out"
    argv = ["run", "--period", PERIOD, "--produktion", str(DEMO / f"produktion_{PERIOD}.csv"),
            "--matning", str(DEMO / f"matning_{PERIOD}.csv"), "--avtalsobjekt", str(DEMO / f"avtalsobjekt_{PERIOD}.csv"),
            "--state", str(tmp_path / name / "state"), "--out", str(out)]
    assert main([*extra, *argv]) == 0
    return out


def files(folder):
    return {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}


def test_a_month_is_its_appendices_and_what_a_person_follows_up_with(tmp_path, capsys):
    out = run(tmp_path, "standard")
    mills = set(pd.read_csv(DEMO / f"matning_{PERIOD}.csv")["mottagningsplats"])
    appendices = {f"bilagor/{mill}.{kind}" for mill in mills for kind in ("html", "xlsx")}
    assert files(out) == appendices | {"avtalsobjekt.csv", "faktura_rader.csv", "sammanfattning.md", "manifest.json"}
    shown = capsys.readouterr().out
    assert "bilagor/" in shown and ".html" in shown and "Utvecklare" not in shown


def test_the_flag_adds_files_and_changes_none(tmp_path, capsys):
    plain, developer = run(tmp_path, "standard"), run(tmp_path, "utvecklare", "--utvecklare")
    capsys.readouterr()
    extra = files(developer) - files(plain)
    assert extra and all(name.startswith("utveckling/") for name in extra)
    assert {"utveckling/matriser_lang.csv", "utveckling/leverans_ao_lang.csv", "utveckling/avstamning_ao.csv",
            "utveckling/krediteringar_ao_lang.csv", "utveckling/uppskattning_mot_skordardata.csv"} <= extra
    assert any(name.endswith(".md") for name in extra) and any("/matriser/" in name for name in extra)
    for name in ("faktura_rader.csv", "avtalsobjekt.csv", "sammanfattning.md"):
        assert (developer / name).read_bytes() == (plain / name).read_bytes()
    # The matrices in the developer output add up to what the invoice says was delivered.
    matrices = pd.read_csv(developer / "utveckling" / "matriser_lang.csv")
    invoice = pd.read_csv(plain / "faktura_rader.csv")
    delivered = invoice.loc[invoice["radtyp"] == "LEVERANS", "volym_m3fub"].sum()
    assert matrices["levererat_m3fub"].sum() == pytest.approx(delivered, abs=0.01)


def test_the_flag_shows_where_the_volume_came_from_and_what_differs_from_the_standard(tmp_path, capsys):
    config = tmp_path / "egen.toml"
    config.write_text("oldest_first = false\n", encoding="utf-8")
    # The flag may stand after the command or before it.
    run(tmp_path, "efter", "--utvecklare")
    after = capsys.readouterr().out
    assert "S1 " in after and "Parametrar som skiljer från standardmodellen: inga" in after
    out = tmp_path / "fore" / "out"
    assert main(["--utvecklare", "run", "--period", PERIOD, "--produktion", str(DEMO / f"produktion_{PERIOD}.csv"),
                 "--matning", str(DEMO / f"matning_{PERIOD}.csv"), "--config", str(config),
                 "--state", str(tmp_path / "fore" / "state"), "--out", str(out)]) == 0
    assert "oldest_first = False" in capsys.readouterr().out
    assert (out / "utveckling" / "matriser_lang.csv").exists()


def test_a_stop_is_one_line_and_the_flag_shows_where_it_came_from(capsys):
    argv = ["run", "--period", PERIOD, "--produktion", str(DEMO / f"produktion_{PERIOD}.csv"),
            "--matning", str(DEMO / f"matning_{PERIOD}.csv"), "--state", "unused", "--out", "unused",
            "--bilaga-langd", "400,370"]
    assert main(argv) == 1
    plain = capsys.readouterr().err
    assert plain.startswith("Fel: ") and "Traceback" not in plain
    assert main([*argv, "--utvecklare"]) == 1
    traced = capsys.readouterr().err
    assert "Traceback" in traced and traced.rstrip().splitlines()[-1].startswith("Fel: ")


def test_the_development_commands_are_listed_only_with_the_flag(capsys):
    for argv, listed in ((["--help"], False), (["--utvecklare", "--help"], True)):
        with pytest.raises(SystemExit):
            main(argv)
        shown = capsys.readouterr().out
        assert ("simulate" in shown) is listed and ("backtest" in shown) is listed
        assert "selftest" in shown and "--utvecklare" in shown
