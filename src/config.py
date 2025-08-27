import os
import yaml

class Config:
    def __init__(self, yaml_path="config.yaml"):
        self.yaml = {}
        if os.path.exists(yaml_path):
            with open(yaml_path, "r") as f:
                self.yaml = yaml.safe_load(f)

    def get(self, key, default=None):
        return self.yaml.get(key, default)

if __name__ == "__main__":
    config = Config()
    newsletter_list = config.get("newsletters", [])
    for newsletter in newsletter_list:
        print(newsletter.get("name"))
    print(config.get("newer_than"))
    print(config.get("preferences").get("interests"))