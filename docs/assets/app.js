document.addEventListener('DOMContentLoaded', () => {
  
  // 1. FAQ Accordion Toggle
  const faqQuestions = document.querySelectorAll('.faq-question');
  
  faqQuestions.forEach(question => {
    question.addEventListener('click', () => {
      // Close all other open accordions
      faqQuestions.forEach(q => {
        if (q !== question) {
          q.classList.remove('active');
        }
      });
      
      // Toggle current accordion
      question.classList.toggle('active');
    });
  });

  // 2. Intersection Observer for Fade-in Animations
  const observerOptions = {
    root: null,
    rootMargin: '0px',
    threshold: 0.15
  };

  const fadeObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target); // Stop observing once it's visible
      }
    });
  }, observerOptions);

  // Apply observer to all elements with fade-in class
  const fadeElements = document.querySelectorAll('.fade-in');
  fadeElements.forEach(el => fadeObserver.observe(el));
});
