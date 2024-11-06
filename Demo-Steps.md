# Demo steps

Use the AKS Store Demo to demo alternate LLM usage - local inferencing instead of Azure OpenAI.

## Pre-requisites

* Install Azure CLI
* Install Azure Developer CLI
* Install Helm
* Install Kubectl
* Install Terraform
* Install git
* Install vscode
* Install Docker Desktop (optional: if you want to build your own Docker images for the sample application)

## Deploy the initial app

Get the basic setup going:

```sh
azd env new
azd config set defaults.subscription "<subscription_id>"
azd config set defaults.location "<region>"
azd env set DEPLOY_AZURE_WORKLOAD_IDENTITY true
azd env set DEPLOY_AZURE_OPENAI true
azd env get-values

azd up
kubectl get service -n pets store-admin -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
kubectl get service -n pets store-frontend -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

eval "$(azd env get-values)"
```

## Update app to use local LLM with KAITO

Follow guide [here](https://moaw.dev/workshop/?src=gh%3Apauldotyu%2Fmoaw%2Flearnlive%2Fworkshops%2Fopensource-models-on-aks-with-kaito%2F&step=0)

Pre-requisite steps:

* Install Resource Providers
* Get whitelisted for Azure OpenAI (gpt-3.5-turbo)
* Get vCPU quota for NCASv3_T4 (minimum 4 GPU cores)

Get the basic setup going:

```sh
az vm list-usage --location ${AZURE_LOCATION} --query "[? contains(localName, 'Standard NCASv3_T4')]" -o table

export AZURE_RESOURCEGROUP_NAME=$AZURE_RESOURCE_GROUP
az identity create   --name mi-kaitoprovisioner   --resource-group $AZURE_RESOURCEGROUP_NAME

KAITO_IDENTITY_PRINCIPAL_ID=$(az identity show \
  --name mi-kaitoprovisioner \
  --resource-group $AZURE_RESOURCEGROUP_NAME \
  --query principalId \
  --output tsv)

KAITO_IDENTITY_CLIENT_ID=$(az identity show \
  --name mi-kaitoprovisioner \
  --resource-group $AZURE_RESOURCEGROUP_NAME \
  --query clientId \
  --output tsv)

az role assignment create \
  --assignee $KAITO_IDENTITY_PRINCIPAL_ID \
  --scope $AZURE_AKS_CLUSTER_ID \
  --role Contributor

az identity federated-credential create \
  --name mi-kaitoprovisioner \
  --identity-name mi-kaitoprovisioner \
  --resource-group $AZURE_RESOURCEGROUP_NAME \
  --issuer $AZURE_AKS_OIDC_ISSUER_URL \
  --subject system:serviceaccount:gpu-provisioner:gpu-provisioner \
  --audience api://AzureADTokenExchange

helm repo add kaito https://azure.github.io/kaito/charts/kaito
helm repo update

cat << EOF > gpu-provisioner-values.yaml
controller:
  env:
  - name: ARM_SUBSCRIPTION_ID
    value: $AZURE_SUBSCRIPTION_ID
  - name: LOCATION
    value: $AZURE_LOCATION
  - name: AZURE_CLUSTER_NAME
    value: $AZURE_AKS_CLUSTER_NAME
  - name: AZURE_NODE_RESOURCE_GROUP
    value: $AZURE_AKS_CLUSTER_NODE_RESOURCEGROUP_NAME
  - name: ARM_RESOURCE_GROUP
    value: $AZURE_RESOURCEGROUP_NAME
  - name: LEADER_ELECT
    value: "false"
workloadIdentity:
  clientId: $KAITO_IDENTITY_CLIENT_ID
  tenantId: $AZURE_TENANT_ID
settings:
  azure:
    clusterName: $AZURE_AKS_CLUSTER_NAME
EOF

cat gpu-provisioner-values.yaml

kubectl create ns gpu-provisioner
kubectl create ns kaito-workspace

helm install gpu-provisioner kaito/gpu-provisioner -f gpu-provisioner-values.yaml -n gpu-provisioner
helm install workspace kaito/workspace -n kaito-workspace

helm ls -A
kubectl get pods -n gpu-provisioner
kubectl get pods -n kaito-workspace

mkdir workspaces

cat << EOF > workspaces/falcon-7b-instruct.yaml
apiVersion: kaito.sh/v1alpha1
kind: Workspace
metadata:
  name: workspace-falcon-7b-instruct
  annotations:
    kaito.sh/enablelb: "False"
resource:
  count: 1
  instanceType: "Standard_NC8as_T4_v3"
  labelSelector:
    matchLabels:
      apps: falcon-7b-instruct
inference:
  preset:
    name: "falcon-7b-instruct"
EOF

# Takes ~10 mins to create the GPU node
kubectl apply -n pets -f workspaces/falcon-7b-instruct.yaml

kubectl describe workspace workspace-falcon-7b-instruct -n pets

kubectl get workspace workspace-falcon-7b-instruct -n pets -w

kubectl logs -n gpu-provisioner -lapp.kubernetes.io\/name=gpu-provisioner -f

kubectl get nodes -o wide
kubectl describe node aks-ws9326a2b96-97574779-vmss000000

# Takes ~9 mins for the container to be ready (downloads the large image with the falcon-7b-instruct model)
kubectl get pod,svc -n pets

# Test the chat completion endpoint for the falcon-7b-instruct model
kubectl run -n pets -it --rm --restart=Never curl --image=curlimages/curl 2>/dev/null -- \
    curl -sX POST http://workspace-falcon-7b-instruct/chat -H "accept: application/json" -H "Content-Type: application/json" -d "{\"prompt\":\"What is a kubernetes?\"}" \
    | jq . 2>/dev/null

# Optional: Run a chainlit python chat app to use the local model (via port forwarding)
cd chatapp/
sudo apt update && sudo apt upgrade -y
sudo apt install software-properties-common -y
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install python3.11
sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

sudo apt install python3-pip
python -m pip install --upgrade setuptools
python -m pip install -r requirements.txt

kubectl port-forward -n pets svc/workspace-falcon-7b-instruct 5000:80
python -m chainlit run app.py -w
# Access chat app at: http://localhost:8080

# Tail logs on model pod to verify it gets used when you chat
kubectl logs -f $(kubectl get pod -l "kaito.sh/workspace=workspace-falcon-7b-instruct" -n pets -o name) -n pets
```

## Update aks store demo to use local model in AKS (falcon7b-instruct)

```sh
kubectl delete cm ai-service-configmap -n pets
kubectl apply -f ai-service-falcon7b-instruct.yaml -n pets
kubectl delete $(kubectl get pod -n pets -l app=ai-service -n pets -o name) -n pets
kubectl get pod -n pets -l app=ai-service -n pets
kubectl get cm ai-service-configmap -n pets -o yaml

# Tail logs on model pod to verify it gets used when you generate a new product name
kubectl logs -f $(kubectl get pod -l "kaito.sh/workspace=workspace-falcon-7b-instruct" -n pets -o name) -n pets
```

## Revert back to Azure OpenaI for AKS store demo

```sh
kubectl delete cm ai-service-configmap -n pets
kubectl apply -f ai-service-azure.yaml -n pets
kubectl delete $(kubectl get pod -n pets -l app=ai-service -n pets -o name) -n pets
kubectl get pod -n pets -l app=ai-service -n pets
kubectl get cm ai-service-configmap -n pets -o yaml

# Tail logs on model pod to verify it does NOT get used when you generate a new product name
kubectl logs -f $(kubectl get pod -l "kaito.sh/workspace=workspace-falcon-7b-instruct" -n pets -o name) -n pets
```

## Resources

* [NCasT4_v3-series VM](https://learn.microsoft.com/en-us/azure/virtual-machines/nct4-v3-series)
* [KAITO falcon7b-instruct inference parameters](https://github.com/Azure/kaito/blob/main/presets/models/falcon/model.go#L99) - check minium requirements to deploy this model
* [KAITO falcon model parameters and usage](https://github.com/Azure/kaito/tree/main/presets/models/falcon)
* [AKS Store Demo](https://github.com/Azure-Samples/aks-store-demo)
* [AKS KAITO add-on](https://learn.microsoft.com/en-us/azure/aks/ai-toolchain-operator)
* [KAITO GitHub upstream repo](https://github.com/Azure/kaito)
* [Soaring to New Heights with Kaito: The Kubernetes AI Toolchain Operator](https://paulyu.dev/article/soaring-with-kaito/) - KAITO blog post with video
* [The Falcon has landed in the Hugging Face ecosystem](https://huggingface.co/blog/falcon) - Blog post on Falcon models
* [aks-kaito-terraform](https://github.com/paolosalvatori/aks-kaito-terraform) - Paolo Salvatori's guide for deploying KAITO on AKS
