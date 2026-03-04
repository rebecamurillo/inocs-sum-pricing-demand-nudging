from .config import InstanceParams, PipelineConfig
from .pipeline import InstancePipeline
from .routing.otp_client import OTPUnavailableError
from .stations.providers import DonkeyRepublicProvider, GBFSProvider


def run_pipeline(config: PipelineConfig, params: InstanceParams, gbfs_provider: GBFSProvider | None = None):
	pipeline = InstancePipeline(config=config, gbfs_provider=gbfs_provider)
	return pipeline.run_all(params)

__all__ = [
	"PipelineConfig",
	"InstanceParams",
	"InstancePipeline",
	"GBFSProvider",
	"DonkeyRepublicProvider",
	"OTPUnavailableError",
	"run_pipeline",
]
