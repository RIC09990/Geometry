"""Apply Linux limits in a separate process before executing the official CLI."""
import os
import subprocess
import sys

if __name__ == '__main__':
    binary, proof = sys.argv[1:]
    if os.name != 'nt':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
        resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024 * 1024,) * 2)
        os.execv(binary, [binary, proof])
    try:
        completed = subprocess.run([binary, proof], timeout=12)
        sys.exit(completed.returncode)
    except subprocess.TimeoutExpired:
        print('NiceGeo proof check timed out.', file=sys.stderr)
        sys.exit(124)
