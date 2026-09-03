"""Minimal JSON-RPC client for the scenario harness (stdlib only)."""
import json
import urllib.request


def rpc(url, method, params=None, timeout=20):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params or []}).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)
    if "error" in data:
        raise RuntimeError(f"{method}: {data['error']}")
    return data["result"]


def hexint(v):
    """int from an RPC hex quantity (or passthrough int/None)."""
    if v is None or isinstance(v, int):
        return v
    return int(v, 16)


def wait_receipt(url, txh, timeout=10.0):
    """Receipt for txh, polling until anvil has mined it. Automine is fast but
    not synchronous under load: a receipt read right after eth_sendTransaction
    can come back None when several anvils share the box."""
    import time
    t0 = time.time()
    while True:
        r = rpc(url, "eth_getTransactionReceipt", [txh])
        if r is not None:
            return r
        if time.time() - t0 > timeout:
            raise RuntimeError(f"tx {txh} not mined after {timeout}s")
        time.sleep(0.05)
