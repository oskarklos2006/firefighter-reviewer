FROM nginx:alpine

# Remove default nginx page
RUN rm /usr/share/nginx/html/index.html

# Copy our UI
COPY index.html /usr/share/nginx/html/index.html

EXPOSE 3000

# Configure nginx to serve on port 3000
RUN sed -i 's/listen\s*80;/listen 3000;/g' /etc/nginx/conf.d/default.conf

CMD ["nginx", "-g", "daemon off;"]