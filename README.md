# Apache2 Log Replay script
This script is for testing production scenarios on identical non-production servers by taking an apache2 log file, ingesting it then replaying each log line, closely mimmicking the timestamp steps, to allow sysadmins to 'relive' or 'replay' events that occurred on production for testing, debugging, and configuration purposes.

Currently the script makes use of the `X-Forwarded-For` header to allow traffic to the target service to appear as if receiving unique IP requests. The webserver/cluster receiving the traffic must be setup as if it were behind a proxy where the `X-Forwarded-For` header would be enabled and in use otherwise it will log all requests as coming directly from the server where the script is being ran.

### Usecases:
- Replaying high-load events to determine rate-limiting effectiveness.
- Replaying regular traffic to A/B test new releases and their ability to handle load.
- Replaying a specific series of requests to determine server lockups or 500 issues.
- Replaying a specific series of requests for CI-CD unit/acceptance testing.
- Replaying malicious service usages to test different architecture solutions.

### Installation:
The `aiohttp` python3 package is a required dependency of this script
```sh
# Pip Install:
pip install aiohttp[speedups]
# Debian/Ubuntu Install:
apt install python3-aiohttp
# Rhel/CentOS Install:
yum install python3-aiohttp

# Next get the script itself:
wget https://raw.githubusercontent.com/MagikEh/log_replay/refs/heads/main/log_replay.py
chmod 750 log_replay.py
```

### Usage:
```sh
usage: apache2_log_replay.py [-h] [--verbose] [--logdateformat LOGDATEFORMAT] [--logformat LOGFORMAT] [--delaystart DELAYSTART] [--maximumTimeDelta MAXIMUMTIMEDELTA] [--initialWorkers INITIALWORKERS] BaseURL LogFile

positional arguments:
  BaseURL               Base URL of the website to target eg:"http[s]://ServerName.domain".
  LogFile               Path to the log file of entries to be replayed against BaseURL.

options:
  -h, --help             show the help message and exit
  --verbose, -v          Output verbosity, default WARN, add more v's for more verbose output.
  --logdateformat, -F    LogFile's timestamp format, defaults to apache2's %t format: %d/%b/%Y:%H:%M:%S %z
  --logformat, -f        LogFile's line format, defaults to apache2's combined format: %h %l %u %t "%r" %>s %O "%{Referer}i" "%{User-Agent}i"
  --delaystart, -d       Period of time (in seconds) to wait between parsing logfile and beginning requests. (default: 1)
  --maximumTimeDelta, -t Period of allowed time (in seconds) that a request may be late by before spawning a new worker. (default: -0.5)
  --initialWorkers, -w   Number of initial workers that the program will start with, more are added as --maximumTimeDelta is breached. (default: 50)

# Examples:
./apache2_log_replay.py --help
./apache2_log_replay.py https://my-cool-internal-vip.sub.domain path/to/my/log/file.log
./apache2_log_replay.py -vvv -d5 -w1 https://my-cool-internal-vip.sub.domain /full/path/to/my/log/file.log

[ctrl]+[c] to exit
```

## Roadmap
- Add a proper delegator, not a fan of having the worker threads 'react' to being late when they pick up a task.
- NGINX support, it's nearly there but will require testing of the current `apache2_patterns` and potentially a CLI switch.
- Make use of other logFile-provided flags:
  - `vhost`
  - `port#`
  - `user agent` (appended?)
  - Request method `GET`/`POST`/`HEAD`/..etc
- Figure out a nicer way to implement a rolling progress output while allowing capture to log file. (pipe into `tee` and see what happens)
- Implement a more elegant mid-script stop mechanism rather than `[ctrl]`+`[c]` and a few thrown exceptions.
- Note in readme, apache2 timestamps are logged when connection closes
  - Future feature to integrate %D into `timestampDelta` to account for this
- Determine the maximum throughput of this script before moving onto multi-core concurrency.

## Known Issues:
- See the `FIXME:` comments in [the log_replay.py script](https://github.com/MagikEh/log_replay/blob/main/log_replay.py).

## Contact:
Please feel free to reach out with questions, PRs, suggestions, feature requests, and bugs in the [MagikEh/log_replay/issues](https://github.com/MagikEh/log_replay/issues)!
