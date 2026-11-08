#!/usr/bin/env bash
# 在允许绑定本地 TCP 端口的机器上运行；先 source 工作空间的 devel/setup.bash。
set -euo pipefail
export ROS_IP=127.0.0.1
unset ROS_HOSTNAME || true
A=${BRIDGE_TEST_MASTER_A_PORT:-12321}
B=${BRIDGE_TEST_MASTER_B_PORT:-12322}
P=${BRIDGE_TEST_PORT:-19091}
TEMP_DIR=$(mktemp -d)
PIDS=()
cleanup() {
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  rm -rf "$TEMP_DIR"
}
trap cleanup EXIT
ROS_MASTER_URI="http://127.0.0.1:$A" roscore -p "$A" >"$TEMP_DIR/master_a.log" 2>&1 & PIDS+=("$!")
ROS_MASTER_URI="http://127.0.0.1:$B" roscore -p "$B" >"$TEMP_DIR/master_b.log" 2>&1 & PIDS+=("$!")
for port in "$A" "$B"; do
  ready=0
  for i in $(seq 1 30); do
    if ROS_MASTER_URI="http://127.0.0.1:$port" rosparam list >/dev/null 2>&1; then ready=1; break; fi
    sleep 1
  done
  if [[ $ready != 1 ]]; then cat "$TEMP_DIR/master_a.log" "$TEMP_DIR/master_b.log"; exit 1; fi
done
ROS_MASTER_URI="http://127.0.0.1:$B" roslaunch oneway_topic_bridge receiver.launch bind_ip:=127.0.0.1 port:="$P" >"$TEMP_DIR/receiver.log" 2>&1 & receiver_pid=$!; PIDS+=("$receiver_pid")
ROS_MASTER_URI="http://127.0.0.1:$A" roslaunch oneway_topic_bridge sender.launch receiver_ip:=127.0.0.1 port:="$P" >"$TEMP_DIR/sender.log" 2>&1 & PIDS+=("$!")
ROS_MASTER_URI="http://127.0.0.1:$A" rostopic pub -r 5 /bridge_example/chatter std_msgs/String 'data: bridge_integration_ok' >"$TEMP_DIR/pub.log" 2>&1 & PIDS+=("$!")
check() {
  local output
  output=$(ROS_MASTER_URI="http://127.0.0.1:$B" timeout 25 rostopic echo -n 1 /bridge_example/chatter) || { cat "$TEMP_DIR/sender.log" "$TEMP_DIR/receiver.log"; return 1; }
  [[ "$output" == *bridge_integration_ok* ]]
  [[ $(ROS_MASTER_URI="http://127.0.0.1:$B" rostopic type /bridge_example/chatter) == std_msgs/String ]]
}
check
kill "$receiver_pid"
wait "$receiver_pid" || true
sleep 3
ROS_MASTER_URI="http://127.0.0.1:$B" roslaunch oneway_topic_bridge receiver.launch bind_ip:=127.0.0.1 port:="$P" >"$TEMP_DIR/receiver2.log" 2>&1 & PIDS+=("$!")
check
printf 'PASS: independent masters, topic/type/payload, receiver restart and reconnect\n'
