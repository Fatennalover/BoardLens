"""Launch upstream Toby in BoardLens's existing macOS Maia runtime."""
import os
import sys


def main():
    script, checkpoint, stockfish = sys.argv[1:]
    environment = dict(os.environ, TOBY_MAIA_WEIGHTS=checkpoint, TOBY_STOCKFISH=stockfish,
                       TOBY_DEVICE='cpu', TOBY_CALCULATOR='Stockfish', TOBY_DEFAULT_DISPLAY='Standard',
                       TOBY_TORCH_THREADS='1', TOBY_SF_THREADS='1', HF_HUB_OFFLINE='1')
    os.execve(sys.executable, [sys.executable, script], environment)


if __name__ == '__main__':
    main()
