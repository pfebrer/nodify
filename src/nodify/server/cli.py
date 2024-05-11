import argparse

from .launch import launch


def nodigui():
    """Command line interface for launching the GUI"""
    parser = argparse.ArgumentParser(
        prog="sgui",
        description="Command line utility to launch nodify's graphical interface.",
    )

    parser.add_argument("--server", action="store_true")
    parser.add_argument("--no-server", dest="server", action="store_false")
    parser.set_defaults(server=True)

    parser.add_argument("--frontend", action="store_true")
    parser.add_argument("--no-frontend", dest="frontend", action="store_false")
    parser.set_defaults(frontend=True)

    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--no-interactive", dest="interactive", action="store_false")
    parser.set_defaults(interactive=True)

    parser.add_argument("--async-mode", type=str, default="threading")
    parser.add_argument("--server-host", type=str, default=None)
    parser.add_argument("--server-port", type=int, default=None)

    parser.add_argument("--server-debug", action="store_true")
    parser.add_argument("--no-server-debug", dest="server_debug", action="store_false")
    parser.set_defaults(server_debug=False)

    args = parser.parse_args()

    async_mode = args.async_mode
    if not args.interactive:
        # Don't force threading async mode since we are not going to interact from a different python
        # thread.
        async_mode = None

    launch(
        async_mode=async_mode,
        frontend=args.frontend,
        server=args.server,
        server_host=args.server_host,
        server_port=args.server_port,
        server_debug=args.server_debug,
        interactive=args.interactive,
    )
