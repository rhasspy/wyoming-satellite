# Websocket Service

## Setup

```shell
script/setup --websockets
```

## Quick Start

In one terminal, run the following

```shell
script/run_websockets --uri 'tcp://0.0.0.0:10701' --websocket-host '0.0.0.0'
```

This will spawn a Wyoming server that listens to and then subsequently publishes events to the provided websocket host and port

```shell
script/run   --name 'my satellite'   --uri 'tcp://0.0.0.0:10700'   --mic-command 'arecord -r 16000 -c 1 -f S16_LE -t raw'   --snd-command 'aplay -r 22050 -c 1 -f S16_LE -t raw' --event-uri 'tcp://0.0.0.0:10701'
```

In another terminal, run the above. This will start the actual satellite and publish events to the Wyoming server in Terminal 1.

If you open the `timers.html` file in a browser, in the Network tab of the Dev Tools, you should see it connect to the websocket.

Alternatively, if you have another app that uses websockets, you should be able to connect to that as well now