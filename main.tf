provider "google" {
  project = "rgc-tfg-uoc"
  region  = "us-central1"
}

resource "google_compute_network" "main-network-02" {
  name    = "main-network-02"
  project = "rgc-tfg-uoc"
 auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "main-network-02-subnet" {
  name          = "main-network-02-subnet"
  region        = "us-central1"
  network       = google_compute_network.main-network-02.name
  ip_cidr_range = "10.1.0.0/24"
  project      = "rgc-tfg-uoc"
}

resource "google_compute_instance" "vm1" {
  name         = "vm1"
  zone         = "us-central1-a"
  project      = "rgc-tfg-uoc"
  machine_type = "e2-micro"
  network_interface {
    subnetwork = google_compute_subnetwork.main-network-02-subnet.name
  }
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
    }
  }

}

resource "google_compute_instance" "vm2" {
  name         = "vm2"
  zone         = "us-central1-a"
  project      = "rgc-tfg-uoc"
  machine_type = "e2-micro"
  network_interface {
    subnetwork = google_compute_subnetwork.main-network-02-subnet.name
  }
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
    }
  }

}

resource "google_compute_firewall" "allow-ssh" {
  name    = "allow-ssh"
  network = google_compute_network.main-network-02.name
  project = "rgc-tfg-uoc"
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

