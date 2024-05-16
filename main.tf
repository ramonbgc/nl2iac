provider "google" {
  project = "rgc-tfg-uoc"
  region  = "us-central1"
}

resource "google_compute_network" "vnet_hub" {
  name                    = "vnet-hub"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "vnet_hub_subnet" {
  name          = "vnet-hub-subnet"
  ip_cidr_range = "10.0.1.0/24"
  network       = google_compute_network.vnet_hub.id
}

resource "google_compute_network" "vnet1" {
  name                    = "vnet1"
  auto_create_subnetworks = false
}

resource "google_compute_network" "vnet2" {
  name                    = "vnet2"
  auto_create_subnetworks = false
}

resource "google_compute_instance" "vnet_hub_instance" {
  name         = "vnet-hub-instance"
  machine_type = "n1-standard-1"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
    }
  }

  network_interface {
    network = google_compute_network.vnet_hub.id
    subnetwork = google_compute_subnetwork.vnet_hub_subnet.id
  }
}

resource "google_compute_instance" "vnet1_instance1" {
  name         = "vnet1-instance1"
  machine_type = "n1-standard-1"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
    }
  }

  network_interface {
    network = google_compute_network.vnet1.id
  }
}

resource "google_compute_instance" "vnet1_instance2" {
  name         = "vnet1-instance2"
  machine_type = "n1-standard-1"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
    }
  }

  network_interface {
    network = google_compute_network.vnet1.id
  }
}

resource "google_compute_instance" "vnet1_instance3" {
  name         = "vnet1-instance3"
  machine_type = "n1-standard-1"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
    }
  }

  network_interface {
    network = google_compute_network.vnet1.id
  }
}

resource "google_compute_instance" "vnet2_instance1" {
  name         = "vnet2-instance1"
  machine_type = "n1-standard-1"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
    }
  }

  network_interface {
    network = google_compute_network.vnet2.id
  }
}

resource "google_compute_instance" "vnet2_instance2" {
  name         = "vnet2-instance2"
  machine_type = "n1-standard-1"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
    }
  }

  network_interface {
    network = google_compute_network.vnet2.id
  }
}

resource "google_compute_firewall" "ssh_firewall" {
  name    = "ssh-firewall"
  network = google_compute_network.vnet_hub.id

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
}

resource "google_compute_network_peering" "vnet_hub_vnet1" {
  name       = "vnet-hub-vnet1"
  network    = google_compute_network.vnet_hub.id
  peer_network = google_compute_network.vnet1.id
}

resource "google_compute_network_peering" "vnet_hub_vnet2" {
  name       = "vnet-hub-vnet2"
  network    = google_compute_network.vnet_hub.id
  peer_network = google_compute_network.vnet2.id
}