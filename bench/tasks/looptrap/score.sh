#!/usr/bin/env bash
# usage: score.sh WORKDIR TASKDIR. Pass: node --test passes and the test file is unchanged.
cd "$1" && cmp -s "$2/files/test/names.test.js" test/names.test.js && node --test >/dev/null 2>&1
