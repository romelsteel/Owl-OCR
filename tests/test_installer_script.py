from tests.conftest import REPO

ISS = (REPO / "packaging" / "installer.iss").read_text(encoding="utf-8")


def test_installer_script():
    assert "PrivilegesRequired=lowest" in ISS
    assert r"DefaultDirName={localappdata}\Programs\OwlOCR" in ISS
    assert r'Name: "{autoprograms}\Owl OCR"' in ISS
    assert 'Name: "desktopicon"' in ISS and "Flags: unchecked" in ISS
    assert "'--remove-data'" in ISS and "usUninstall" in ISS and "IDNO" in ISS
    assert r"compiler:Languages\Czech.isl" in ISS
    assert "OutputBaseFilename=OwlOCR-{#AppVersion}-setup" in ISS
    assert "function InitializeUninstall(): Boolean;" in ISS and "CloseAppFirst" in ISS


def test_uninstall_never_wipes_the_install_folder_wholesale():
    """I-1: the folder is fixed (no directory page) and the uninstaller removes only what it installed."""
    assert "DisableDirPage=yes" in ISS
    assert "[UninstallDelete]" not in ISS
    assert 'Name: "{app}"' not in ISS


def test_failed_data_removal_is_reported():
    """I-2: a non-zero exit of --remove-data shows a message naming the data folder (EN + CS)."""
    assert "english.RemoveDataFailed=" in ISS and "czech.RemoveDataFailed=" in ISS
    assert "(ResultCode <> 0)" in ISS and "CustomMessage('RemoveDataFailed')" in ISS
    assert r"{userappdata}\OwlOCR\location.txt" in ISS and r"{localappdata}\OwlOCR" in ISS
    czech = next(line for line in ISS.splitlines() if line.startswith("czech.RemoveDataFailed="))
    assert "můžete" in czech and "%1" in czech
