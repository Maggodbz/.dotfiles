"""Entry point: python3 -m jarvis"""

from .app import JarvisApp


def main() -> None:
    app = JarvisApp()
    app.run()


if __name__ == "__main__":
    main()
