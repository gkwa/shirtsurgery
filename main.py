import argparse
import json
import logging
import pathlib
import sys

import aws_regions.endpoints
import boto3
import botocore.exceptions
import yaml

self_path = pathlib.Path(__file__)

logging.basicConfig(filename=f"{self_path.stem}.log", level=logging.DEBUG)


data = pathlib.Path("data")
data.mkdir(parents=True, exist_ok=True)

amis = data / "amis"
amis.mkdir(parents=True, exist_ok=True)

parser = argparse.ArgumentParser()

parser.add_argument(
    "-r", "--refetch", action="store_true", help="refresh data?", default=False
)
args = parser.parse_args()


def refetch_amis_all_regions():
    region_names = aws_regions.endpoints.get_regions()

    for region_name in region_names:
        client = boto3.client("ec2", region_name)
        print(f"checking region {region_name}")

        try:
            response = client.describe_images(Owners=["self"])
            path = amis / f"{region_name}.json"
            path.write_text(json.dumps(response, indent=2))
        except botocore.exceptions.ClientError:
            print(
                f"ERROR: can't access region {region_name}, skipping...",
                file=sys.stderr,
            )
            continue


def debug(cdi_images, records):
    logging.debug(f"length(cdi_images): {len(cdi_images)}")
    logging.debug(f"length(records): {len(records)}")

    for record in cdi_images:
        region = record["region"]
        name = record["ami"]
        out = f"{name}:{region}"
        logging.debug(out)


if args.refetch or len(list(amis.glob("*.json"))) < 5:
    refetch_amis_all_regions()

records = []

for path in amis.glob("*.json"):
    with open(path) as fh:
        rec = json.load(fh)
        for ami in rec["Images"]:
            name = ""
            if "Tags" in ami:
                lst = [tag["Value"] for tag in ami["Tags"] if tag["Key"] == "Name"]
                name = "" if not lst else lst[0]

            out = {
                "region": path.stem,
                "ami": ami["Name"],
                "ami_id": ami["ImageId"],
            }
            records.append(out)


logging.debug(json.dumps(records, indent=2))
logging.debug(json.dumps(sorted([x["ami"] for x in records])))

ami_filter = "sbx-cdi 2022-08-10T01-52-35.178Z"

cdi_images = list(filter(lambda x: ami_filter in x["ami"], records))
cdi_images = sorted(cdi_images, key=lambda i: (i["ami"], i["region"]), reverse=True)

cdi2 = {}
for dct in cdi_images:
    region = dct["region"]
    cdi2[region] = {"ami": dct["ami_id"]}

out = yaml.dump(cdi2)
print(out)
