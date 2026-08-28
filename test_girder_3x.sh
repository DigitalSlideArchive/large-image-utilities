#!/usr/bin/env bash
set -e

echo "--------------------------------"
echo "  Girder 3.x Maintenance Tests  "
echo "--------------------------------"

# --- NODE 14 SETUP ---
echo ">>> Configuring Node 14"
NODE_14_PATH="/home/ubuntu/.nvm/versions/node/v14.21.3/bin"
if [ ! -d "$NODE_14_PATH" ]; then
    source "$HOME/.nvm/nvm.sh"
    NODE_14_BIN=$(nvm which 14) || true
    if [ -z "$NODE_14_BIN" ]; then
        nvm install 14
        NODE_14_BIN=$(nvm which 14)
    fi
    NODE_14_PATH=$(dirname $(dirname $NODE_14_BIN))
fi
export PATH="$NODE_14_PATH:$PATH"
echo "Node version: $(node --version)"

# --- MONGODB CHECK ---
mongosh --eval "db.runCommand('ping').ok" > /dev/null 2>&1 || {
    echo "!!! WARNING: MongoDB connection check failed.";
}

# --- PYTHON 3.9 & VENV ---
echo ">>> Configuring Python 3.9"
export PYENV_ROOT="$HOME/.pyenv"
if [ -d "$PYENV_ROOT" ]; then
    export PATH="$PYENV_ROOT/bin:$PYENV_ROOT/shims:$PATH"
fi
PYTHON_BIN="$HOME/.pyenv/versions/3.9.25/bin/python3.9"
if [ ! -x "$PYTHON_BIN" ]; then
    echo ">>> Python 3.9 not found at $PYTHON_BIN, installing"
    pyenv install 3.9.25
fi

VENV_DIR="/home/ubuntu/girder_env"
if [ -d "$VENV_DIR" ]; then rm -rf "$VENV_DIR"; fi

echo ">>> Creating Virtualenv at $VENV_DIR"
$PYTHON_BIN -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
echo ">>> Python version: $(python --version)"

# --- Install Girder and dependencies ---
cd /home/ubuntu/girder

echo ">>> Installing Python Dependencies..."
pip install --upgrade pip setuptools wheel
pip install --editable clients/python
pip install --editable ".[sftp,mount]" --requirement requirements-dev.txt

# --- Environment Variables ---
export PYTHON_EXECUTABLE="$VENV_DIR/bin/python"
export JASMINE_TIMEOUT="15000"
export CIRCLE_WORKING_DIRECTORY=/home/ubuntu
export CMAKE_POLICY_VERSION_MINIMUM=3.5

echo ">>> Starting Tests..."

echo "--------------------------------"
echo ">>> [Job: web-lint-test]"
cd girder
npm ci
npm run lint
cd ..

echo "--------------------------------"
echo ">>> [Job: server-lint-test]"
tox -e lint
tox -e public_names
tox -e docs

echo "--------------------------------"
echo ">>> [Job: server-pytest-test]"
mkdir -p girder/build/test/results
tox -e pytest_circleci

echo "--------------------------------"
echo ">>> [Job: server-legacy-test]"
rm -rf /home/ubuntu/girder_build
mkdir /home/ubuntu/girder_build
pushd /home/ubuntu/girder_build
TEST_GROUP=python ctest --extra-verbose --script "$CIRCLE_WORKING_DIRECTORY/girder/.circleci/ci_test.cmake" --exclude-regex '^server_pytest_core$'
popd

echo "--------------------------------"
echo ">>> [Job: web-test]"

npm install -g npm-force-resolutions

if [ ! -f /etc/ssl/openssl.cnf ] || [ ! -s /etc/ssl/openssl.cnf ]; then
    if [ -f /usr/lib/ssl/openssl.cnf ]; then
        sudo cp /usr/lib/ssl/openssl.cnf /etc/ssl/openssl.cnf 2>/dev/null || echo "Failed to copy openssl.cnf"
    else
        echo "Error: openssl.cnf is missing and no fallback found."
        exit 1
    fi
fi

echo ">>> Installing phantomjs-prebuilt globally..."
npm install -g phantomjs-prebuilt 2>&1 | tail -n 10 || {
    npm install -g --allow-scripts phantomjs-prebuilt 2>&1 | tail -n 10
}

if [ -z "${PYTHON_EXECUTABLE}" ]; then
    export PYTHON_EXECUTABLE="/home/ubuntu/girder_env/bin/python"
fi

echo ">>> Installing and building Girder..."
# We must ensure we are using Node 14 for the build
export PATH="$HOME/.nvm/versions/node/v14.21.3/bin:$PATH"
source "$HOME/.nvm/nvm.sh" && nvm use 14 > /dev/null

rm -rf /home/ubuntu/girder_build
mkdir /home/ubuntu/girder_build
girder build --dev

if [ ! -d /home/ubuntu/girder_env/share/girder/static ]; then
    mkdir -p /home/ubuntu/girder_env/share/girder/static
    cp -fR /home/ubuntu/girder/girder/static/* /home/ubuntu/girder_env/share/girder/static/
fi

echo ">>> Running Web Tests..."
pushd /home/ubuntu/girder_build
TEST_GROUP=browser ctest --extra-verbose --script "$CIRCLE_WORKING_DIRECTORY/girder/.circleci/ci_test.cmake"
popd

echo "--------------------------------"
echo ">>> [Job: integration-test]"
rm -rf /home/ubuntu/girder_build
mkdir /home/ubuntu/girder_build
pushd /home/ubuntu/girder_build
cmake ../girder -DPYTHON_VERSION=3.9 -DPYTHON_EXECUTABLE=$CIRCLE_WORKING_DIRECTORY/girder_env/bin/python
make --jobs=3
JASMINE_TIMEOUT=15000 ctest --parallel 3 --extra-verbose --label-regex girder_integration
popd

echo "--------------------------------"
echo ">>> [Job: Coverage]"
cd /home/ubuntu/girder
tox -e coverage
npm run coverage

echo "--------------------------------"
echo "  All tests complete  "
