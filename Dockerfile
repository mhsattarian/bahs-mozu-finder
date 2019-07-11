# our base image
FROM python:2.7.162.7.16-onbuild

# specify the port number the container should expose
EXPOSE 5002

# run the application
CMD ["python", "./app.py"]