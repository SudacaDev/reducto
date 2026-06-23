#!/usr/bin/env bash
# publish.sh — Publica Reducto en PyPI
# Uso: ./publish.sh [--test]   (--test sube a TestPyPI primero)

set -e

echo "🧹 Limpiando builds anteriores..."
rm -rf dist/ build/ *.egg-info

echo "📦 Construyendo paquete..."
python -m build

echo "✅ Verificando paquete..."
twine check dist/*

if [ "$1" == "--test" ]; then
  echo "🚀 Subiendo a TestPyPI..."
  twine upload --repository testpypi dist/*
  echo ""
  echo "Probá con:"
  echo "  pip install --index-url https://test.pypi.org/simple/ reducto"
  echo "  uv tool install --index-url https://test.pypi.org/simple/ reducto"
else
  echo "🚀 Subiendo a PyPI..."
  twine upload dist/*
  echo ""
  echo "Ya podés instalar con:"
  echo "  pip install reducto"
  echo "  uv tool install reducto"
fi
