
import os
import httpx
import jinja2
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from typing import Optional, Dict, Any

class T2IService:
    def __init__(self):
        self.service_url = os.getenv("T2I_SERVICE_URL", "http://localhost:8999")
        self.method = os.getenv("T2I_METHOD", "t2i-service") # "t2i-service" or "pillow"
        
        # Setup Jinja2 environment
        template_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates")
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_dir),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
        
        # Load environment config
        self.icon_base_url = os.getenv("ICON_BASE_URL", "exports/icons/skills")
        if self.icon_base_url.startswith(".") or not (self.icon_base_url.startswith("http") or self.icon_base_url.startswith("/")):
             # Resolve relative path to absolute file path for local rendering
             # Assuming exports is at project root
             project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
             self.icon_base_url = "file:///" + os.path.join(project_root, self.icon_base_url).replace("\\", "/")
             
        # Inject global config
        self.env.globals['config'] = {
            'ICON_BASE_URL': self.icon_base_url,
            'ICON_SECTION_URL': os.getenv("ICON_SECTION_URL", self.icon_base_url.replace("skills", "section"))
        }

    async def generate_image(self, template_name: str, data: Dict[str, Any]) -> bytes:
        """
        Generate an image from a template and data.
        """
        if self.method == "t2i-service":
            try:
                return await self._generate_via_service(template_name, data)
            except Exception as e:
                print(f"T2I Service failed: {e}. Falling back to Pillow.")
                return await self._generate_via_pillow(template_name, data)
        else:
            return await self._generate_via_pillow(template_name, data)

    async def _generate_via_service(self, template_name: str, data: Dict[str, Any]) -> bytes:
        template = self.env.get_template(template_name)
        rendered_html = template.render(**data)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.service_url}/text2img/generate",
                json={
                    "html": rendered_html,
                    # We can also send tmpl/tmpldata if the service supports it directly, 
                    # but rendering locally gives us more control and consistency.
                    # The service docs say "html" OR "tmpl" + "tmpldata".
                    # Let's send "html" for simplicity as we already rendered it.
                },
                timeout=30.0
            )
            response.raise_for_status()
            # The service returns the image data directly?
            # The docs say:
            # POST /text2img/generate -> returns JSON with ID?
            # "bool json: Whether to return JSON format (returns an id)"
            # If json is false (default?), it might return the image directly.
            # But usually it returns the image content.
            # Let's assume it returns the image content unless json=True is passed.
            return response.content

    async def _generate_via_pillow(self, template_name: str, data: Dict[str, Any]) -> bytes:
        # Fallback: Create a simple text image
        # We can't easily render HTML with Pillow without a browser engine.
        # So we will just dump the data as text.
        
        text_content = ""
        # A simple recursive function to dump dict to text
        def dump_data(d, indent=0):
            text = ""
            for k, v in d.items():
                if isinstance(v, dict):
                    text += " " * indent + f"{k}:\n" + dump_data(v, indent + 2)
                elif isinstance(v, list):
                    text += " " * indent + f"{k}:\n"
                    for item in v:
                        if isinstance(item, dict):
                            text += " " * (indent + 2) + "- \n" + dump_data(item, indent + 4)
                        else:
                            text += " " * (indent + 2) + f"- {item}\n"
                else:
                    text += " " * indent + f"{k}: {v}\n"
            return text

        # If data has a 'text_fallback' key (which we might add), use that.
        if 'text_fallback' in data:
            text_content = data['text_fallback']
        else:
            text_content = dump_data(data)

        # Create image
        img_width = 800
        font_size = 20
        # Estimate height
        lines = text_content.split('\n')
        img_height = max(100, len(lines) * (font_size + 5) + 40)
        
        image = Image.new('RGB', (img_width, img_height), color=(255, 255, 255))
        draw = ImageDraw.Draw(image)
        
        # Load a font - try generic, then default
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except IOError:
            font = ImageFont.load_default()
        
        draw.text((20, 20), text_content, fill=(0, 0, 0), font=font)
        
        buf = BytesIO()
        image.save(buf, format='PNG')
        return buf.getvalue()

# Singleton instance
_t2i_instance = None

def get_t2i_service() -> T2IService:
    global _t2i_instance
    if _t2i_instance is None:
        _t2i_instance = T2IService()
    return _t2i_instance
