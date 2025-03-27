from PIL import Image

def create_mosaic(image_paths, mosaic_size, output_path):
    # Determine the size of each image in the mosaic
    image_width, image_height = mosaic_size

    # Create a new blank image for the mosaic
    mosaic = Image.new('RGB', (image_width * 3, image_height * 3))

    # Iterate over the image paths and paste them into the mosaic
    for i, image_path in enumerate(image_paths):
        image = Image.open(image_path).resize((image_width, image_height))
        x = (i % 3) * image_width
        y = (i // 3) * image_height
        mosaic.paste(image, (x, y))

    # Save the final mosaic image
    mosaic.save(output_path)

# Example usage
image_paths = [
    'image1.jpg',
    'image2.jpg',
    'image3.jpg',
    'image4.jpg',
    'image5.jpg',
    'image6.jpg',
    'image7.jpg',
    'image8.jpg',
    'image9.jpg'
]
mosaic_size = (100, 100)  # Set the size of each image in the mosaic
output_path = 'mosaic.jpg'
create_mosaic(image_paths, mosaic_size, output_path)
