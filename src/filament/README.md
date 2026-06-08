```
# brew install etcd
# etcd --version
# brew services start etcd
# brew services list
# etcdctl endpoint health
brew install consul
consul version
~~brew services start consul~~ doesn't work
```

```
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo update

helm install consul hashicorp/consul --set global.name=consul --create-namespace -n consul

helm upgrade consul hashicorp/consul \
  -n consul \
  --set ui.enabled=true \
  --set ui.service.type=NodePort

kubectl port-forward svc/consul-ui -n consul 8500:80
```

```
brew install zookeeper
brew services start zookeeper
```
