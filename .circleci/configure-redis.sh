#!/usr/bin/env bash
set -e

apt-get update -qq && apt-get install -y --no-install-recommends \
  redis-server
