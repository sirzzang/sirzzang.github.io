# GPU 1장과 영속 홈을 가진 개발 세션. stop하면 Deployment가 지워지고 홈 PVC는 남는다.
terraform {
  required_providers {
    coder = {
      source = "coder/coder"
    }
    kubernetes = {
      source = "hashicorp/kubernetes"
    }
  }
}

provider "coder" {}
provider "kubernetes" {} # Coder 서버 파드의 서비스 계정을 쓴다

data "coder_workspace" "me" {}
data "coder_workspace_owner" "me" {}

locals {
  name = "coder-${lower(data.coder_workspace_owner.me.name)}-${lower(data.coder_workspace.me.name)}"
}

resource "coder_agent" "main" {
  os   = "linux"
  arch = "arm64"
}

resource "kubernetes_persistent_volume_claim" "home" {   # count가 없어 정지해도 남는다
  wait_until_bound = false
  metadata {
    name      = "${local.name}-home"
    namespace = "coder"
  }
  spec {
    access_modes = ["ReadWriteOnce"]
    resources {
      requests = {
        storage = "1Gi"
      }
    }
  }
}

resource "kubernetes_deployment" "main" {
  count            = data.coder_workspace.me.start_count   # 시작이면 1, 정지면 0
  wait_for_rollout = false # GPU가 없으면 파드가 대기하므로 빌드는 기다리지 않는다
  metadata {
    name      = local.name
    namespace = "coder"
  }
  spec {
    replicas = 1
    strategy {
      type = "Recreate"
    }
    selector {
      match_labels = {
        session = local.name
      }
    }
    template {
      metadata {
        labels = {
          session = local.name
        }
      }
      spec {
        security_context {
          run_as_user = 1000
          fs_group    = 1000
        }
        container {
          name              = "dev"
          image             = "codercom/enterprise-base:ubuntu"
          image_pull_policy = "IfNotPresent"
          command           = ["sh", "-c", coder_agent.main.init_script]
          env {
            name  = "CODER_AGENT_TOKEN"
            value = coder_agent.main.token
          }
          resources {
            limits = {
              "nvidia.com/gpu" = "1"
            }
          }
          volume_mount {
            name       = "home"
            mount_path = "/home/coder"
          }
          volume_mount {
            name       = "tmp"
            mount_path = "/tmp"
          }
        }
        volume {
          name = "home"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim.home.metadata[0].name
          }
        }
        volume {
          name = "tmp"
          empty_dir {}
        }
      }
    }
  }
}
