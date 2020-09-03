#Financial Disclosure Extractor Docker Image

## Quick start

Pull new docker image (if any) and run image

    docker-compose pull
    docker-compose up

You can run the docker run command or just docker-compose up.

##Usage
Once the docker container is up and running, the container exposes 
port :5001 to accept and process financial disclosures.

Currently two api endpoints are exposted at 

    http://disclosure-extractor:5001/  
    
    http://disclosure-extractor:5001/url


The first is a test of the container returns a json object or None
    
    returns:
    {"success": True, "msg": "Docker container running."}
    
The second accepts a post request

    data = {
        "url": "URL to a Financial disclosure PDF"
    }
    resp = requests.post("http://disclosure-extractor:5001/url", json=data)
    
    returns:
    
    A dictionary of data from a financial disclosure if able to process it
    

##More information

This docker image/container runs python 3.7 and extracts information from 
financial disclosures using our [Disclosure Extractor Repo](https://github.com/freelawproject/disclosure-extractor)  

See [CL Disclosure Extractor Repo](https://github.com/freelawproject/courtlistener-disclosure-extractor)
for more details on the docker image and API endpoints.
