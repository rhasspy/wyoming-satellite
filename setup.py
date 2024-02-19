#!/usr/bin/env python3
from pathlib import Path
from typing import List

import setuptools
from setuptools import setup

this_dir = Path(__file__).parent
module_dir = this_dir / "wyoming_satellite"
version_path = module_dir / "VERSION"
version = version_path.read_text(encoding="utf-8").strip()


def get_requirements(req_path: Path) -> List[str]:
    if not req_path.is_file():
        return []

    requirements: List[str] = []
    with open(req_path, "r", encoding="utf-8") as req_file:
        for line in req_file:
            line = line.strip()
            if not line:
                continue

            requirements.append(line)

    return requirements


install_requires = get_requirements(this_dir / "requirements.txt")
extras_require = {
    "silerovad": get_requirements(this_dir / "requirements_vad.txt"),
    "webrtc": get_requirements(this_dir / "requirements_audio_enhancement.txt"),
}


# -----------------------------------------------------------------------------

setup(
    name="wyoming_satellite",
    version="1.1.0",
    description="Wyoming server for remote voice satellite",
    url="http://github.com/rhasspy/wyoming-satellite",
    author="Michael Hansen",
    author_email="mike@rhasspy.org",
    packages=setuptools.find_packages(),
    package_data={
        "wyoming_satellite": [str(p.relative_to(module_dir)) for p in (version_path,)]
    },
    install_requires=install_requires,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    keywords="rhasspy wyoming satellite",
    extras_require=extras_require,
    entry_points={
        "console_scripts": ["wyoming-satellite = wyoming_satellite:__main__.run"]
    },
)
