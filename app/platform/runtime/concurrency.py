"""按主机可用内存自适应收紧并发上限。

纯 Docker 容器（无 lxcfs）下 /proc/meminfo 反映的是宿主机内存，
正是发生全局 OOM 的那一层，因此这是正确的观测点。
"""


def _mem_available_mb() -> int | None:
    """读取 /proc/meminfo 的 MemAvailable（MiB）；读不到返回 None。"""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024  # kB -> MiB
    except OSError:
        return None
    return None


def effective_concurrency(configured: int) -> int:
    """把配置并发数按当前可用内存分层收紧；读不到内存则信任配置值。"""
    configured = max(1, int(configured))
    avail = _mem_available_mb()
    if avail is None:
        return configured
    if avail < 512:
        cap = 2
    elif avail < 1024:
        cap = 4
    elif avail < 2048:
        cap = 6
    else:
        return configured
    return min(configured, cap)
