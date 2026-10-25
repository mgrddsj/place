# Place v1

Please see `architecture.png` for the architecture diagram of this application.

## How I setup this application on EC2

### Create an EC2 instance

1. Go to the AWS Management Console and navigate to the EC2 service.
2. Go to "Key Pairs" under "Network & Security" and upload an ssh public key.
3. Go to "Instances" and click on "Launch Instance".
4. Use the defaults (t3.micro), I used Debian 13 as the OS. Select the key pair uploaded. 
5. Launch the instance.
6. Go to "Security Groups" under "Network & Security" and select the security group associated with the instance.
7. Edit the inbound rules, add a rule to allow traffic on port 8080 (for webServer) and port 8081 (for socketServer) from 0.0.0.0/0.


### Connect to the instance and set up the docker

1. Get the public IP address of the instance from the EC2 dashboard.
2. Open a terminal and connect to the instance using SSH: 
   ```bash
   ssh -i /path/to/private-key.pem admin@ec2-public-ip
   ```
3. Update the package list and install Docker:
   ```bash
    sudo apt update
    sudo apt install docker.io -y
   ```
4. Allow the current user to run Docker commands without `sudo`:
   ```bash
   sudo usermod -aG docker $USER
   ```
5. Log out and log back in to the server to apply the group changes.

### Set up the application

1. Clone the repository and enter this version's directory:
   ```bash
   git clone https://github.com/mgrddsj/place.git
   cd place/legacy/v1
   ```

2. Build the images:
   ```bash
   ./build.bash
   ```

3. Run the application:
   ```bash
   docker swarm init
   ./doit.bash
   ```

4. Open a web browser and navigate to `http://ec2-public-ip:8080` to access the application.

