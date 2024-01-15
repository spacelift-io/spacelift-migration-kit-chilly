import click

from spacemk.generator import Generator


@click.command(help="Generate Terraform code to manage Spacelift stacks for the Jenkins workflow.")
def generate_jenkins_stacks():
    generator = Generator()
    generator.generate(template_name="jenkins.tf.jinja")
