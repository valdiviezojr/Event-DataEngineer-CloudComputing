"""Comprobaciones exclusivamente de lectura para la cuenta y destinos de AWS."""
import os
import re

import seed_config as C


def aws_clients(region):
    import boto3
    from botocore.config import Config

    if any(os.getenv(name) for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                                        "http_proxy", "https_proxy", "all_proxy")):
        raise ValueError("Preflight AWS requiere conexión directa sin proxy")
    if not re.fullmatch(r"[a-z]{2}-[a-z]+-\d+", region) or region.startswith(("cn-", "us-gov-")):
        raise ValueError("Solo se admiten regiones de la partición AWS comercial")
    session = boto3.Session(region_name=region)
    config = Config(ignore_configured_endpoint_urls=True, retries={"mode": "standard", "max_attempts": 5})
    client = lambda service: session.client(service, config=config)
    return session, client


def keys(hash_key, range_key):
    return {(hash_key, "HASH"), (range_key, "RANGE")}


def key_schema(raw):
    return {(field["AttributeName"], field["KeyType"]) for field in raw}


def inspect_table(client, region, account, name, *, load):
    table = client.describe_table(TableName=name)["Table"]
    arn = f"arn:aws:dynamodb:{region}:{account}:table/{name}"
    if (table["TableArn"] != arn or table["TableStatus"] != "ACTIVE"
            or key_schema(table["KeySchema"]) != keys("PK", "SK")
            or {field["AttributeName"]: field["AttributeType"] for field in table["AttributeDefinitions"]}
            != dict(PK="S", SK="S", GSI1PK="S", GSI1SK="S")
            or table.get("LocalSecondaryIndexes") or table.get("Replicas")):
        raise ValueError(f"{name}: tabla, claves o replicación incompatibles")
    indexes = table.get("GlobalSecondaryIndexes", [])
    if (len(indexes) != 1 or indexes[0]["IndexName"] != "GSI1"
            or indexes[0]["IndexStatus"] != "ACTIVE"
            or indexes[0]["Projection"]["ProjectionType"] != "ALL"
            or key_schema(indexes[0]["KeySchema"]) != keys("GSI1PK", "GSI1SK")):
        raise ValueError(f"{name}: GSI1 incompatible")
    if load:
        if table.get("StreamSpecification", {}).get("StreamEnabled"):
            raise ValueError(f"{name}: DynamoDB Streams activo; puede tener consumidores fuera de Lambda")
        destinations = client.describe_kinesis_streaming_destination(TableName=name).get("KinesisDataStreamDestinations", [])
        if any(s["DestinationStatus"] != "DISABLED" for s in destinations):
            raise ValueError(f"{name}: destino Kinesis activo o indeterminado")
        try:
            policy = client.get_resource_policy(ResourceArn=arn)
        except client.exceptions.PolicyNotFoundException:
            pass
        else:
            if policy.get("Policy") is not None:
                raise ValueError(f"{name}: política de recurso fuera de la simulación")
    return {"arn": arn, "id": table["TableId"]}


def prove_role(session, client, principal, region):
    credentials = session.get_credentials()
    if credentials is None or credentials.method != "iam-role":
        raise ValueError("Se requieren credenciales del perfil EC2 obtenidas por IMDS")
    match = re.fullmatch(r"arn:aws:sts::(\d{12}):assumed-role/([^/]+)/i-[0-9a-f]+", principal["Arn"])
    if not match or match[1] != principal["Account"]:
        raise ValueError("STS no identifica una sesión de perfil de instancia EC2")
    organizations = client("organizations")
    try:
        organizations.describe_organization()
    except organizations.exceptions.AWSOrganizationsNotInUseException:
        pass
    else:
        raise ValueError("Cuenta en AWS Organizations: no se acreditaron todos los controles organizativos")
    ec2 = client("ec2")
    for page in ec2.get_paginator("describe_vpc_endpoints").paginate(
        Filters=[{"Name": "service-name", "Values": [f"com.amazonaws.{region}.dynamodb"]}],
    ):
        if any(endpoint["State"] != "deleted" for endpoint in page["VpcEndpoints"]):
            raise ValueError("Existe un endpoint VPC de DynamoDB cuya política efectiva no se ha acreditado")
    iam = client("iam")
    return iam, iam.get_role(RoleName=match[2])["Role"]["Arn"]


def simulate_put(iam, role, arn, *, recruitment=False):
    actions = ["PutItem", "ConditionCheckItem"] if recruitment else ["PutItem"]
    for tenant in C.TENANTS:
        leading = {"ContextKeyName": "dynamodb:LeadingKeys",
                   "ContextKeyValues": [f"TENANT#{tenant}"], "ContextKeyType": "stringList"}
        for action in actions:
            context = [leading]
            if action == "PutItem":
                context.insert(0, {"ContextKeyName": "dynamodb:EnclosingOperation",
                                   "ContextKeyValues": ["TransactWriteItems"], "ContextKeyType": "string"})
            decision = iam.simulate_principal_policy(
                PolicySourceArn=role, ActionNames=[f"dynamodb:{action}"], ResourceArns=[arn],
                ContextEntries=context,
            )
            results = decision["EvaluationResults"]
            if (decision.get("IsTruncated") or len(results) != 1 or results[0].get("MissingContextValues")
                    or results[0]["EvalDecision"] != "allowed"):
                raise ValueError(f"{arn} {tenant}: permiso transaccional {action} sin acreditar")


def inspect_aws(region, tables, *, load, check_iam=True):
    account = os.environ["SEED_AWS_ACCOUNT_ID"]
    if not re.fullmatch(r"\d{12}", account):
        raise ValueError("SEED_AWS_ACCOUNT_ID debe contener el número de cuenta esperado")
    session, client = aws_clients(region)
    principal = client("sts").get_caller_identity()
    if principal["Account"] != account:
        raise ValueError("STS devolvió una cuenta distinta de SEED_AWS_ACCOUNT_ID")
    dynamo = client("dynamodb")
    info = {service: inspect_table(dynamo, region, account, name, load=load)
            for service, name in tables.items()}
    if load and check_iam:
        if os.getenv("SEED_AWS_ACADEMY") == "1":
            if not re.fullmatch(
                r"arn:aws:sts::\d{12}:assumed-role/voclabs/.+",
                principal["Arn"]
            ):
                raise ValueError("Sesion AWS Academy no reconocida")

            from botocore.exceptions import ClientError

            for service, table_name in tables.items():
                for tenant in C.TENANTS:
                    key = {
                        "PK": {"S": f"TENANT#{tenant}"},
                        "SK": {"S": "SEED_PERMISSION_PROBE"}
                    }

                    operations = ["Put"]
                    if service == "recruitment":
                        operations.append("ConditionCheck")

                    for operation in operations:
                        action = {
                            "TableName": table_name,
                            "ConditionExpression":
                                "attribute_exists(PK) AND attribute_not_exists(PK)"
                        }
                        action["Item" if operation == "Put" else "Key"] = key

                        try:
                            dynamo.transact_write_items(
                                TransactItems=[{operation: action}]
                            )
                        except ClientError as exc:
                            reasons = exc.response.get("CancellationReasons", [])
                            if (
                                exc.response["Error"]["Code"] != "TransactionCanceledException"
                                or [r.get("Code") for r in reasons] != ["ConditionalCheckFailed"]
                            ):
                                raise
                        else:
                            raise RuntimeError("Resultado inesperado de prueba")

                        print(f"OK | {table_name} | {tenant} | {operation}", flush=True)
        else:
            iam, role = prove_role(session, client, principal, region)
            for service, table in info.items():
                simulate_put(iam, role, table["arn"], recruitment=service == "recruitment")
    return dynamo, info
