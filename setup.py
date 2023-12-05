#!/usr/bin/env python3
from pathlib import Path

import setuptools
from setuptools import setup

this_dir = Path(__file__).parent

requirements = []
requirements_path = this_dir / "requirements.txt"
if requirements_path.is_file():
    with open(requirements_path, "r", encoding="utf-8") as requirements_file:
        requirements = requirements_file.read().splitlines()


# -----------------------------------------------------------------------------

setup(
    name="wyoming_handle_external",
    version="1.0.0",
    description="Wyoming server for remote voice satellite",
    url="http://github.com/rhasspy/wyoming-satellite",
    author="Michael Hansen",
    author_email="mike@rhasspy.org",
    packages=setuptools.find_packages(),
    install_requires=requirements,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    keywords="rhasspy wyoming satellite",
    extras_require={
        "silerovad": ["onnxruntime>=1.10.0,<2", "numpy<1.26"],
        "webrtc": ["webrtc-noise-gain==1.2.3"],
    },
    entry_points={
        "console_scripts": ["wyoming-satellite = wyoming_satellite:__main__.run"]
    },
)
