import os


class MLflowAdapter:
    def __init__(self, tracking_uri: str, token: str | None = None):
        import mlflow
        from mlflow.tracking import MlflowClient

        mlflow.set_tracking_uri(tracking_uri)
        if token:
            os.environ["MLFLOW_TRACKING_TOKEN"] = token
        self.client = MlflowClient()

    def fetch_registered_models(self) -> list[dict]:
        """
        Read-only. Returns admin metadata only.
        Never fetches model weights or training data.
        ADR-012 approved exception — customer-provided
        MLflow URI + credentials.
        """
        models: list[dict] = []
        try:
            for registered_model in self.client.search_registered_models():
                try:
                    latest_versions = self.client.get_latest_versions(
                        registered_model.name,
                        stages=["Production", "Staging", "None"],
                    )
                    for model_version in latest_versions:
                        run = None
                        if model_version.run_id:
                            try:
                                run = self.client.get_run(model_version.run_id)
                            except Exception:
                                run = None
                        models.append(
                            {
                                "name": registered_model.name,
                                "version": model_version.version,
                                "stage": model_version.current_stage,
                                "tags": dict(registered_model.tags or {}),
                                "description": registered_model.description or "",
                                "training_data_source": (
                                    run.data.tags.get("training_data") if run is not None else None
                                ),
                                "run_id": model_version.run_id,
                            }
                        )
                except Exception:
                    continue
        except Exception as exc:
            raise RuntimeError(f"MLflow connection failed: {str(exc)}") from exc
        return models

    def map_to_aibom_components(self, models: list[dict]) -> list[dict]:
        components: list[dict] = []
        for model in models:
            components.append(
                {
                    "component_type": "base_model",
                    "name": model["name"],
                    "version": str(model["version"]),
                    "source": "mlflow_registry",
                    "source_integration": "mlflow",
                    "is_third_party": False,
                }
            )
            if model.get("training_data_source"):
                components.append(
                    {
                        "component_type": "training_data",
                        "name": model["training_data_source"],
                        "source": "mlflow_run_tag",
                        "source_integration": "mlflow",
                        "is_third_party": False,
                    }
                )
        return components
