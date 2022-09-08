import argparse
import json
import logging
import pathlib
import re
import stat
import sys

import aws_regions.endpoints
import boto3
import botocore.exceptions
import ndjson

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
ami_filter = "sbx-cdi 2022-09-07T22-23-09.989Z"

cdi_images = list(filter(lambda x: ami_filter in x["ami"], records))
cdi_images = sorted(cdi_images, key=lambda i: (i["ami"], i["region"]), reverse=True)

cdi2 = []
for dct in cdi_images:
    region = dct["region"]
    x = {region: {"ami": dct["ami_id"]}}
    cdi2.append(x)

pathlib.Path("doc.json").write_text(json.dumps(cdi2, indent=2))

with open("doc.ndjson", "w") as f:
    ndjson.dump(cdi2, f)

with open("doc.ts", "w") as ts:
    with open("doc.ndjson") as f:
        reader = ndjson.reader(f)

        for post in reader:
            y = str(post)
            y = re.sub("^{", "", y)
            y = re.sub("}$", "", y)
            ts.write(f"{y},\n")

compath = pathlib.Path("commmands.sh")

make_public = []
make_private = []

with open(compath, "w") as com:
    for dct in cdi2:
        for region in dct:
            ami = dct[region]["ami"]
            public = f"aws ec2 modify-image-attribute --region {region} --image-id {ami} --launch-permission 'Add=[{{Group=all}}]'"  # noqa: E501
            private = f"aws ec2 modify-image-attribute --region {region} --image-id {ami} --launch-permission 'Remove=[{{Group=all}}]'"  # noqa: E501
            make_public.append(public)
            make_private.append(private)

    for cmd in make_public:
        com.write(f"{cmd}\n")

    for cmd in make_private:
        com.write(f"#{cmd}\n")


compath.chmod(path.stat().st_mode | stat.S_IEXEC)
