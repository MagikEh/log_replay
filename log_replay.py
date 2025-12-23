#!/usr/bin/env python3

# Replays an apache2 log file at the provided service. Useful to test connection patterns from prod on non-operational hardware.

# pip install aiohttp[speedups]
import aiohttp
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import logging
import re

# Apache2 %flag to regex mapping
# Stolen and adapted from Kassner's log-parser: https://github.com/kassner/log-parser/blob/master/src/LogParser.php#L23-L47
apache2_patterns = {
  r'%%' : r'(?P<percent>\%)',
  r'%a' : r'(?P<remoteIp>{{PATTERN_IP_ALL}})',
  r'%A' : r'(?P<localIp>{{PATTERN_IP_ALL}})',
  r'%h' : r'(?P<host>[a-zA-Z0-9\-\._:]+)',
  r'%l' : r'(?P<logname>(?:-|[\w-]+))',
  r'%m' : r'(?P<requestMethod>OPTIONS|GET|HEAD|POST|PUT|DELETE|TRACE|CONNECT|PATCH|PROPFIND)',
  r'%H' : r'(?P<requestProtocol>HTTP/(1\.0|1\.1|2\.0))',
  r'%p' : r'(?P<port>\d+)',
  r'\%\{(local|canonical|remote)\}p' : r'(?P<\\1Port>\d+)',
  r'%r' : r'(?P<request>(?:(?:[A-Z]+) .+? HTTP/(1\.0|1\.1|2\.0))|-|)',
  r'%t' : r'\[(?P<time>\d{2}/(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/\d{4}:\d{2}:\d{2}:\d{2} (?:-|\+)\d{4})\]',
  r'%u' : r'(?P<user>(?:-|[\w\-\.@]+))',
  r'%U' : r'(?P<URL>.+?)',
  r'%v' : r'(?P<serverName>([a-zA-Z0-9]+)([a-z0-9.-]*))',
  r'%V' : r'(?P<canonicalServerName>([a-zA-Z0-9]+)([a-z0-9.-]*))',
  r'%>s': r'(?P<status>\d{3}|-)',
  r'%b' : r'(?P<responseBytes>(\d+|-))',
  r'%T' : r'(?P<requestTime>(\d+\.?\d*))',
  r'%O' : r'(?P<sentBytes>(\d+|-))',
  r'%I' : r'(?P<receivedBytes>(\d+|-))',
  r'%{(?P<name1>[a-zA-Z]+)(?P<name2>[-]?)(?P<name3>[a-zA-Z]+)}i' : r'(?P<Header\1\3>.*?)',
  r'%D' : r'(?P<timeServeRequest>[0-9]+)',
  r'%S' : r'(?P<scheme>http|https)',
};

apache2_log_date_format = "%d/%b/%Y:%H:%M:%S %z"
apache2_log_combined_format = "%h %l %u %t \"%r\" %>s %O \"%{Referer}i\" \"%{User-Agent}i\""
apache2_log_format = apache2_log_combined_format
total_log_lines = 0

class URLRequest:
  def __init__(self, lineNum, url, timestamp, ip):
    self.lineNum = lineNum
    self.url = url
    self.timestamp = datetime.strptime(timestamp, apache2_log_date_format)
    self.ip = ip
    logging.debug(f'New {self}')
  def __str__(self):
    return f'URLRequest #{self.lineNum}: {self.ip} @ {self.timestamp} to "{self.url}"'

# FIXME: Incomplete functionality
async def delegator(workerPool, workQueue, session):
  while workQueue.qsize() > 0: # FIXME: make this request blocking.. (Delegator thread always highest priority)
    task = await workQueue.get()
    delta = (urlRequest.timestamp - datetime.now(timezone.utc)).total_seconds()
    if (delta <= 0):
      pass
      # Loop the worker pool and give the first available worker something to do
      # if no workers available, create a new one and give it the work
      # determine how to 'pause' and 'trigger' workers
      #   worker given work
      #   worker do work
      #   worker sleep/pause
      #   if no new worker work, seppuku (until qsize() < min)
    else:
      await asyncio.sleep(delta)

async def worker(workerPool, workQueue, total_log_lines, session):
  while workQueue.qsize() > 0:
    try:
      urlRequest = await workQueue.get()
      delta = (urlRequest.timestamp - datetime.now(timezone.utc)).total_seconds()
      print(f'\rRequesting log line {urlRequest.lineNum}/{total_log_lines} ({urlRequest.lineNum/total_log_lines*100:.2f}%) @{urlRequest.timestamp} (in {delta:.2f}sec)',end="", flush=True)
      if (delta < args.maximumTimeDelta): #FIXME: current workaround until delegator is defined
        workerPool.append(asyncio.create_task(worker(workerPool, workQueue, total_log_lines, session)))
        logging.warning(f'Log line #{urlRequest.lineNum} is late, time-delta of {delta:.2f} seconds, added worker #{len(workerPool)}.')
      await asyncio.sleep(delta)
      async with session.get(urlRequest.url, headers={'X-Forwarded-For': f"{urlRequest.ip}", 'User-Agent': 'log_replay'}) as response:
        logging.debug(f"{urlRequest} returned {response.status}")

    except (asyncio.TimeoutError, aiohttp.ServerDisconnectedError) as e:
      logging.warning(f'{urlRequest} returned {e}.')
    except Exception as e:
      logging.exception(f'{urlRequest} returned raised exception: \"{e}\"')
    finally:
      workQueue.task_done()


def parseURLs(baseURL, logfile, delayTime):
  # parse logs based on apache2%flags --> regex mappings
  logging.info(f'Generating apache2 log format regex mappings')
  # Create a regex pattern to match any key in apache2_patterns
  apache2_pattern = "|".join(key for key in apache2_patterns.keys())

  # Replace all instances of keys with values in apache2_log_format using lambda function
  def replace_match(match):
      value = apache2_patterns.get(match.group(0))
      if value is None:
        # It wasn't a 1:1 match, we need to search for it
        for key in apache2_patterns.keys():
          if re.match(key, match.group(0)):
            # pattern is not properly using the returned capture groups, we need to manually do this..
            value = re.sub(key, apache2_patterns[key], match.group(0))

      logging.debug(f'Mapping {match.group(0)} to {value}')
      return value
  regexer = re.compile(r'' + re.sub(apache2_pattern, replace_match, apache2_log_format))

  logging.info(f'Parsing logfile {logfile}')
  #FIXME: get rid of requests[] and replace with workQueue
  requests=[]
  try:
    with open(logfile, 'r', encoding='utf-8') as file:
      lineNum = 0
      for line in file:
        lineNum +=1
        match = regexer.match(line) # Strictly check log lines based on user inputted formatting requirements.
        if match is None:
          logging.warning(f"Unable to match {logfile}:{lineNum} '{line}'")
        else:
          m = match.groupdict()
          # FIXME: change baseURL to instead use [canocal]serverName if present
          if m['request'] != '-' and m['request'].split(' ')[0] == 'GET': #FIXME: Allow more than just GET requests
            requests.append(URLRequest(lineNum, f"{baseURL}{m['request'].split(' ')[1]}", m['time'], m['host'])) #FIXME: still using apache2 formatted request split1, may break for nginx?
  except Exception as e:
    logging.exception(f'LogFile ingest raised exception: {e}')

  logging.info(f'Sorting parsed requests and finding delta from now.')
  # Sort URLs by timestamp and offset schedule time
  requests.sort(key=lambda x: x.timestamp)
  # Set the earliest scheduled request to start delaytime seconds from now and offset all following requests
  timestampDelta = datetime.now(timezone.utc) + timedelta(seconds=delayTime) - requests[0].timestamp
  workQueue = asyncio.Queue()
  for request in requests:
    request.timestamp += timestampDelta
    workQueue.put_nowait(request)
  return workQueue


# define function to add task to pool in main, pass pointer to said function as callback to all workers, when worker finds it was behind, it runs the callback which adds a worker to the workerPool.

async def main():
  logging.info(f'Parsing log requests')
  workQueue = parseURLs(args.BaseURL, args.LogFile, args.delaystart)

  logging.info(f'Setting up worker threads')
  session = aiohttp.ClientSession(trust_env=True,
                                 # timeout=aiohttp.ClientTimeout(total=5),
                                  connector=aiohttp.TCPConnector(limit=0,limit_per_host=0)
                                  )
  #FIXME: Add deligator thread that generates workers before the queue delta falls behind (currently we're adding workers only when a worker notices it is already behind)
  workerPool = []
  for i in range(args.initialWorkers):
    workerPool.append(asyncio.create_task(worker(workerPool, workQueue, workQueue.qsize(), session)))

  logging.info(f'Running scheduled requests')
  await workQueue.join()

  logging.info(f'Cleaning up {len(workerPool)} worker resources')
  #for task in workerPool:
  #  task.cancel()
  await asyncio.gather(*workerPool, return_exceptions=True)
  session.close()
  logging.info("Run complete.")


## CLI Options:
parser = argparse.ArgumentParser()
parser.add_argument('--verbose', '-v', action='count', default=0,                           help='Output verbosity, default WARN, add more v\'s for more verbose output.')
parser.add_argument('--logdateformat', '-F',           default=apache2_log_date_format,     help='LogFile\'s timestamp format, defaults to apache2\'s %%t format: %(default)s')
parser.add_argument('--logformat', '-f',               default=apache2_log_combined_format, help='LogFile\'s line format, defaults to apache2\'s combined format: %(default)s')
parser.add_argument('--delaystart', '-d',              default=1, type=int,                 help='Period of time (in seconds) to wait between parsing logfile and beginning requests. (default: %(default)s)')
parser.add_argument('--maximumTimeDelta', '-t',        default=-0.5, type=int,              help='Period of allowed time (in seconds) that a request may be late by before spawning a new worker. (default: %(default)s)')
parser.add_argument('--initialWorkers', '-w',          default=50, type=int,                help='Number of initial workers that the program will start with, more are added as --maximumTimeDelta is breached. (default: %(default)s)')
parser.add_argument('BaseURL',                                                              help='Base URL of the website to target eg:"http[s]://ServerName.domain".') #FIXME: Make optional when vhost log parsing implemented
parser.add_argument('LogFile',                                                              help='Path to the log file of entries to be replayed against BaseURL.')

args = parser.parse_args()
apache2_log_date_format = args.logdateformat
apache2_log_format = args.logformat

loggingFormat = '\r%(asctime)s [%(levelname)s]: %(message)s'
if(args.verbose == 0):
  logging.basicConfig(level=logging.WARNING, format=loggingFormat)
elif(args.verbose == 1):
  logging.basicConfig(level=logging.INFO, format=loggingFormat)
elif(args.verbose < 1):
  logging.basicConfig(level=logging.DEBUG, format=loggingFormat)

if __name__ == "__main__":
  asyncio.run(main())
