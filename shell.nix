{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  buildInputs = with pkgs; [
    python312
    python312Packages.pip
    python312Packages.virtualenv
    python312Packages.setuptools
    python312Packages.wheel
    # Add netifaces directly from nixpkgs to avoid compilation issues
    python312Packages.netifaces
    docker
    docker-compose
    nats-server
    natscli
    stdenv.cc.cc.lib
    gcc
    zlib
    libffi
    openssl
  ];
  
  shellHook = ''
    # Set library path for compiled Python packages
    export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib:$LD_LIBRARY_PATH"
    
    # Ensure Python version consistency
    export PYTHONPATH="${pkgs.python312Packages.netifaces}/${pkgs.python312.sitePackages}:$PYTHONPATH"
    
    echo "Internet Measurement Network Development Environment"
    echo "=================================================="
    echo "Python version: $(python --version)"
    echo "Docker version: $(docker --version)"
    echo "NATS server version: $(nats-server --version)"
    echo ""
    echo "To install Python dependencies, run:"
    echo "pip install -r server/requirements.txt"
    echo ""
    echo "To start fastapi server, run:"
    echo "cd server && fastapi run main.py"
    echo ""
    echo "To start the NATS server, run:"
    echo "nats-server -n newton -m 8222 -DVV"
    echo ""
    echo "To start an agent, run:"
    echo "python3 -m aiori_agent"
  '';
}