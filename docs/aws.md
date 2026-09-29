# Applying the AWS environment

`terraform/envs/aws` builds a VPC across three AZs, an EKS cluster with a managed node group and the same monitoring stack as the local cluster. CI validates it on every push but does not apply it.

This costs money while it runs (EKS control plane, NAT gateway, three nodes). Destroy it when you are done.

```bash
cd terraform/envs/aws
export TF_VAR_grafana_admin_password='choose-something'
terraform init
terraform plan -out plan.tfplan
terraform apply plan.tfplan

$(terraform output -raw configure_kubectl)
```

Then push the image to a registry the cluster can pull from (for example ECR), point the `images:` entry at it in a new `k8s/overlays/aws` overlay without the `imagePullPolicy: Never` patch, and `kubectl apply -k` it.

Before using this for anything real:

- Configure the S3 backend (commented in `main.tf`) so state is shared and locked
- Set `single_nat_gateway = false` so one AZ failing does not take out egress for the others
- Run CI with GitHub OIDC to an IAM role instead of long lived keys, with plan on pull requests and apply on merge behind an approval

Tear down:

```bash
terraform destroy
```
