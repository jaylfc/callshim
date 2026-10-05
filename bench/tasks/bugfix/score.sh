#!/usr/bin/env bash
# usage: score.sh WORKDIR TASKDIR. Pass: node --test passes and the test file is unchanged.
cd "$1" && cmp -s "$2/files/test/stats.test.js" test/stats.test.js && node --test >/dev/null 2>&1
