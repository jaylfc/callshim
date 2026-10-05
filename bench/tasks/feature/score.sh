#!/usr/bin/env bash
# usage: score.sh WORKDIR TASKDIR. Pass: visible and hidden tests pass (hidden tests copied in only for scoring).
cd "$1" && cp "$2/hidden/hidden.test.js" test/zz-hidden.test.js && node --test >/dev/null 2>&1; rc=$?; rm -f test/zz-hidden.test.js; exit $rc
