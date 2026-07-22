from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="fluxV",
    version="0.3.0",
    author="fluxV Team",
    description="Async-First Python Library for MetaTrader 5 Algorithmic Trading",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/fluxV",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Financial and Insurance Industry",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Topic :: Office/Business :: Financial :: Investment",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.12",
    install_requires=[
        "MetaTrader5>=5.0.45",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "python-dotenv>=1.0.0",
        "typing-extensions>=4.5.0",
        "aiohttp>=3.8.0",
        "beautifulsoup4>=4.11.0",
        "lxml>=4.9.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0",
            "flake8>=6.0",
            "mypy>=1.0",
            "ruff>=0.1.0",
        ],
        "visualization": [
            "plotly>=5.0",
            "matplotlib>=3.0",
        ],
        "all": [
            "plotly>=5.0",
            "matplotlib>=3.0",
            "jupyter>=1.0",
            "ipywidgets>=8.0",
        ],
    },
)