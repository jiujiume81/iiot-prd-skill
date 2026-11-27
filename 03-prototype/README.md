# 03 原型设计

```bash
SUITE="$PWD"        # 在套件根目录下执行（含 01-business/ shared/ 的那一层）
python3 $SUITE/shared/assets/container/src/build.py --proto $PWD/<产品>.proto.json --out $PWD/dist/index.html
python3 $SUITE/shared/bin/check_contract.py <产品>.proto.json
```

**出口**：容器单文件 html + `pages[].componentTree` / `interactions` / `prd` + 页面标注 + 同源 PRD（md/html）。四道验收全绿才算交付：全场 `check_contract` → `check_parity` → `check_interact`。

**上游**：`iiot-req-analysis`（02）。入口条件是 proto 存在且 `check_contract --half req` 绿。
**下游**：无，交给开发。

**不改业务语义**：`capabilities` / `stateMachines` / `requirements` 只读。要改流程回 02。
