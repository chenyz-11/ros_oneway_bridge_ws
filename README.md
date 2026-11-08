# ROS Noetic 单向话题桥

在两台 Ubuntu 20.04 / ROS Noetic 主机各自运行独立的 ROS master：发送端订阅配置中的话题，通过一条 TCP 连接发送原始 ROS 序列化数据；接收端在自己的 master 下以**相同绝对话题名、消息类型、MD5 和数据**发布。支持多个话题、自定义消息、网络断线自动重连及发送端锁存话题的转发。桥接进程无需导入具体消息类型；需要解析、显示或订阅自定义消息的应用仍须在本机安装并 source 与发送端一致的消息包。

## 1. 安装和编译

两台机器都安装 ROS Noetic 和 catkin，分别运行（从本项目复制 `src/oneway_topic_bridge` 目录到两台机器）：

```bash
mkdir -p ~/ros_oneway_bridge_ws/src
# 将 oneway_topic_bridge 文件夹复制到 ~/ros_oneway_bridge_ws/src/ 下
cd ~/ros_oneway_bridge_ws
source /opt/ros/noetic/setup.bash
catkin_make
source devel/setup.bash
```

每个新终端都需要 source `/opt/ros/noetic/setup.bash` 和上述工作空间的 `devel/setup.bash`。不要复制另一台机器编译产生的 `build`、`devel`；请各自编译。

## 2. 配置话题

编辑两台机器的 `src/oneway_topic_bridge/config/topics.yaml`，确保话题列表一致，例如：

```yaml
topics:
  - /bridge_example/chatter
  - /camera/image_raw
  - /lidar/points
queue_size: 10
max_message_bytes: 33554432
```

话题名必须是完整的绝对名称。添加或删除话题后重启两端桥接节点；不需要为每种消息编写代码。`queue_size` 是发送端全部话题共享的消息队列容量，同时是接收端每个 ROS publisher 的队列容量；满时发送端丢弃最旧消息。`max_message_bytes` 是单条序列化消息上限（两端都需足够大，默认 32 MiB），大图像或点云请根据实际大小调整。队列和大消息会占用相应内存。可通过 launch 的 `config:=/绝对路径/文件.yaml` 指定其他配置。

## 3. 启动

假设发送端 A 为 `192.168.1.10`、接收端 B 为 `192.168.1.20`。每台机器上每个终端应使用该机器自己的 master：

```bash
# A 的各个终端
export ROS_MASTER_URI=http://localhost:11311
export ROS_IP=192.168.1.10
# B 的各个终端
export ROS_MASTER_URI=http://localhost:11311
export ROS_IP=192.168.1.20
```

如之前设置过 `ROS_HOSTNAME`，请先 `unset ROS_HOSTNAME`，避免覆盖 ROS_IP。IP 改成对应机器真实网卡地址。A、B 分别启动自己的 `roscore`，然后先在 B 启动：

```bash
roslaunch oneway_topic_bridge receiver.launch bind_ip:=0.0.0.0 port:=19090
```

在 A 启动：

```bash
roslaunch oneway_topic_bridge sender.launch receiver_ip:=192.168.1.20 port:=19090
```

两机 TCP 网络必须可达，接收端防火墙须允许 A 访问 B 的 TCP 19090 端口。桥接连接方向始终为 A 到 B，不需要跨机器访问对方的 ROS master 或 ROS 节点端口。`bind_ip` 也可设置为 B 的指定网卡地址。

## 4. 验证

在 A 的另一终端发布测试数据：

```bash
rostopic pub -r 2 /bridge_example/chatter std_msgs/String 'data: hello_bridge'
```

在 B 的另一终端：

```bash
rostopic type /bridge_example/chatter
rostopic echo /bridge_example/chatter
```

预期类型为 `std_msgs/String`，内容为 `hello_bridge`。接收端只有在收到该话题首条消息后才创建发布者，普通非锁存消息可能因订阅连接建立而丢失最初几条；持续发布即可观察。实际部署应再用目标消息类型和两台实体设备验证网络和吞吐量。

## 5. 扩展与约束

- 新话题：修改两端 YAML 并重启；源数据的 ROS 消息定义经连接头转发，不需要修改桥接代码。消息类型变更时接收端重建 publisher，ROS 订阅者可能需要重新连接。避免同一话题同时由不同类型或不同锁存属性的发布者发送，也避免接收端同名话题已有不兼容的发布者。
- 锁存：接收端按源发布者的锁存属性创建 publisher，并缓存收到的最后一条。断线后缓存仍会保留；发送端锁存发布者在连接重建时会重新提供消息。源端已退出且没有新消息时，接收端不会自动撤销旧缓存。
- TCP 保序但本桥不是可靠消息队列：断线期间队列可能溢出，发送失败的当前消息会丢弃，无法确认对方应用已收到；重连后可能发送队列中较旧的数据。多话题共享一条连接，大消息或慢网络可能延迟其他话题；按实际带宽、延迟、数据频率和内存规划配置。
- 不转发服务、参数、TF 的特殊语义或 master 注册信息；`/tf`、`/tf_static` 可作为普通话题配置。时间戳和坐标系字段原样保留，不进行时钟同步或坐标变换。不能用本桥双向连接相同话题，否则可能形成回环。
- 协议未提供认证、加密及消息完整性保护，接收端允许列表只限制话题名，不能阻止冒充发送端；仅在可信网络使用，跨不可信网络请通过 VPN 或安全隧道传输并限制端口访问。接收端一次只处理一个发送连接。
- 默认发送 `message_definition` 的上限为 1 MiB；各端 ROS 消息定义及 MD5 应保持一致。

## 6. 开发和测试

```bash
source ~/ros_oneway_bridge_ws/devel/setup.bash
python3 ~/ros_oneway_bridge_ws/src/oneway_topic_bridge/test/test_offline.py
~/ros_oneway_bridge_ws/src/oneway_topic_bridge/test/integration.sh
```

集成脚本在本机启动端口 12321、12322 的独立 master 和端口 19091 的桥，验证话题名、类型、内容以及接收端重启后重连；端口已占用时可用 `BRIDGE_TEST_MASTER_A_PORT`、`BRIDGE_TEST_MASTER_B_PORT`、`BRIDGE_TEST_PORT` 环境变量调整。运行要求系统允许本机 TCP 端口绑定。脚本不会替代双机实际链路和目标消息的验证。

实现入口是 `scripts/sender.py`、`scripts/receiver.py`，帧编解码在 `scripts/bridge_common.py`。两端协议需要同时更新；修改消息格式时建议先补充兼容性测试。排错时查看 launch 终端输出，检查两端配置、源话题是否持续发布、IP、端口和防火墙，并确保各终端连接本机 master。
