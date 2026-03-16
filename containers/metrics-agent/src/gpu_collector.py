"""GPU metrics collector using DCGM (primary) with pynvml fallback."""

import logging
import threading
import time

logger = logging.getLogger(__name__)

# DCGM field IDs
DCGM_FI_DEV_GPU_TEMP = 150
DCGM_FI_DEV_POWER_USAGE = 155
DCGM_FI_DEV_GPU_UTIL = 203
DCGM_FI_DEV_MEM_COPY_UTIL = 204
DCGM_FI_DEV_FB_USED = 252
DCGM_FI_PROF_SM_ACTIVE = 1002
DCGM_FI_PROF_PIPE_TENSOR_ACTIVE = 1004
DCGM_FI_PROF_DRAM_ACTIVE = 1005


class GPUCollector:
    """Collects GPU metrics via DCGM or pynvml fallback."""

    def __init__(self, poll_interval: int = 5):
        self._poll_interval = poll_interval
        self._lock = threading.Lock()
        self._metrics: dict[str, float] = {}
        self._use_dcgm = False
        self._dcgm_handle = None
        self._dcgm_group = None
        self._dcgm_field_group = None
        self._nvml_handle = None
        self._running = False
        self._thread: threading.Thread | None = None

        self._init_backend()

    def _init_backend(self):
        """Try DCGM first, fall back to pynvml."""
        try:
            import pydcgm
            import dcgm_agent
            import dcgm_structs
            import dcgm_fields

            dcgm_handle = pydcgm.DcgmHandle(opMode=dcgm_structs.DCGM_OPERATION_MODE_MANUAL)
            self._dcgm_handle = dcgm_handle

            # Create group with all GPUs
            dcgm_system = dcgm_handle.GetSystem()
            gpu_ids = dcgm_system.discovery.GetAllSupportedGpuIds()
            if not gpu_ids:
                raise RuntimeError("No GPUs found via DCGM")

            group = pydcgm.DcgmGroup(
                dcgm_handle,
                groupName="metrics-agent",
                groupType=dcgm_structs.DCGM_GROUP_EMPTY,
            )
            for gpu_id in gpu_ids:
                group.AddGpu(gpu_id)
            self._dcgm_group = group

            # Create field group
            field_ids = [
                DCGM_FI_DEV_GPU_UTIL,
                DCGM_FI_DEV_MEM_COPY_UTIL,
                DCGM_FI_PROF_SM_ACTIVE,
                DCGM_FI_PROF_PIPE_TENSOR_ACTIVE,
                DCGM_FI_DEV_GPU_TEMP,
                DCGM_FI_DEV_POWER_USAGE,
                DCGM_FI_DEV_FB_USED,
                DCGM_FI_PROF_DRAM_ACTIVE,
            ]
            field_group = pydcgm.DcgmFieldGroup(
                dcgm_handle,
                name="agent-fields",
                fieldIds=field_ids,
            )
            self._dcgm_field_group = field_group

            # Set up watches
            try:
                dcgm_system.introspect.state.toggle(dcgm_structs.DCGM_INTROSPECT_STATE.ENABLED)
            except (AttributeError, dcgm_structs.DCGMError):
                logger.debug("DCGM introspect toggle not available, skipping")
            group.samples.WatchFields(
                field_group,
                updateFreq=self._poll_interval * 1000000,  # microseconds
                maxKeepAge=30.0,
                maxKeepSamples=5,
            )

            self._use_dcgm = True
            self._gpu_ids = gpu_ids
            logger.info("GPU collector initialized with DCGM (GPUs: %s)", gpu_ids)

        except Exception as e:
            logger.warning("DCGM unavailable (%s), falling back to pynvml", e)
            self._use_dcgm = False
            try:
                import pynvml
                pynvml.nvmlInit()
                self._nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                logger.info("GPU collector initialized with pynvml fallback")
            except Exception as e2:
                logger.error("Neither DCGM nor pynvml available: %s", e2)
                self._nvml_handle = None

    def start(self):
        """Start the background polling thread."""
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("GPU collector polling started (interval=%ds)", self._poll_interval)

    def stop(self):
        """Stop the background polling thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)

    def get_metrics(self) -> dict[str, float]:
        """Return the latest GPU metrics snapshot (thread-safe)."""
        with self._lock:
            return dict(self._metrics)

    def _poll_loop(self):
        while self._running:
            try:
                if self._use_dcgm:
                    self._poll_dcgm()
                elif self._nvml_handle is not None:
                    self._poll_pynvml()
            except Exception:
                logger.exception("Error polling GPU metrics")
            time.sleep(self._poll_interval)

    def _poll_dcgm(self):
        import dcgm_agent
        import dcgm_structs

        dcgm_agent.dcgmUpdateAllFields(self._dcgm_handle.handle, 1)

        latest = self._dcgm_group.samples.GetLatest(self._dcgm_field_group).values

        field_map = {
            DCGM_FI_DEV_GPU_UTIL: "gpu_gpu_utilization",
            DCGM_FI_DEV_MEM_COPY_UTIL: "gpu_memory_utilization",
            DCGM_FI_PROF_SM_ACTIVE: "gpu_sm_activity",
            DCGM_FI_PROF_PIPE_TENSOR_ACTIVE: "gpu_tensor_active",
            DCGM_FI_DEV_GPU_TEMP: "gpu_temp",
            DCGM_FI_DEV_POWER_USAGE: "gpu_power",
            DCGM_FI_DEV_FB_USED: "gpu_memory_used",
            DCGM_FI_PROF_DRAM_ACTIVE: "gpu_dram_active",
        }

        # DCGM blank sentinel values indicate no data available
        DCGM_BLANK_SENTINELS = {
            0x7ffffff0,   # DCGM_INT32_BLANK
            0x7ffffffff0, # DCGM_INT64_BLANK
        }

        new_metrics = {}
        for gpu_id in self._gpu_ids:
            gpu_data = latest.get(gpu_id, {})
            for field_id, metric_name in field_map.items():
                field_data = gpu_data.get(field_id)
                if field_data and len(field_data) > 0:
                    val = field_data[-1].value
                    if not isinstance(val, (int, float)):
                        continue
                    # Skip DCGM blank sentinel values
                    if isinstance(val, int) and val in DCGM_BLANK_SENTINELS:
                        continue
                    new_metrics[metric_name] = float(val)

        with self._lock:
            self._metrics = new_metrics

    def _poll_pynvml(self):
        import pynvml

        handle = self._nvml_handle
        new_metrics = {}

        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        new_metrics["gpu_gpu_utilization"] = float(util.gpu)
        new_metrics["gpu_memory_utilization"] = float(util.memory)

        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        new_metrics["gpu_temp"] = float(temp)

        power = pynvml.nvmlDeviceGetPowerUsage(handle)
        new_metrics["gpu_power"] = float(power) / 1000.0  # milliwatts -> watts

        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        new_metrics["gpu_memory_used"] = float(mem_info.used) / (1024 * 1024)  # bytes -> MB

        # Profiling metrics (sm_activity, tensor_active, dram_active) not available via pynvml

        with self._lock:
            self._metrics = new_metrics
