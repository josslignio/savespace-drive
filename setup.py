from setuptools import setup

setup(
    name="savespace-drive",
    version="0.1.1",
    package_dir={"": "src"},
    extras_require={"bureau": ["pywebview>=5"]},  # fenêtre native (APP2) ; sans elle, « bureau » ouvre le navigateur
    entry_points={
        "console_scripts": ["savespace-drive=savespace_drive.cli:main"],
    },
)
