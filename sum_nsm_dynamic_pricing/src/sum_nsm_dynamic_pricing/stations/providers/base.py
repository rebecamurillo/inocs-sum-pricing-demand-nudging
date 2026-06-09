# Source: Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/API_call_instance_generation_instance_validation.ipynb
from abc import ABC, abstractmethod
from pathlib import Path


class GBFSProvider(ABC):
    @abstractmethod
    def fetch_station_information(self, output_dir: Path) -> Path:
        raise NotImplementedError
