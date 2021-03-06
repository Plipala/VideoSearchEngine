import argparse
import torch
import torch.nn as nn
from torch.autograd import Variable
import numpy as np
import os
import pickle
from data_loader import get_loader 
from build_vocab import Vocabulary
from model import EncoderCNN, DecoderRNN
from torch.nn.utils.rnn import pack_padded_sequence
from torchvision import transforms
from tqdm import (
    tqdm,
    trange
)

from TensorLogger import (
    Logger
)

# Device configuration
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

def test(encoder, decoder, data_loader, step_count, tensor_board_writer):
    criterion = nn.CrossEntropyLoss()
    loss_total = 0
    loss_count = 0
    for i, (images, captions, lengths) in enumerate(tqdm(data_loader)):
        # Set mini-batch dataset
        images = Variable(images, requires_grad=False).to(device)
        # print(images.shape)
        captions = captions.to(device)
        targets = pack_padded_sequence(captions, lengths, batch_first=True)[0]

        features = encoder(images)
        outputs = decoder(features, captions, lengths)
        loss = criterion(outputs, targets)
        decoder.zero_grad()
        encoder.zero_grad()
        loss_total += loss.item()
        loss_count += 1
        if torch.cuda.is_available():
                torch.cuda.empty_cache()
    tensor_board_writer.scalar_summary("dev_loss", float(loss_total) / loss_count, step_count)
    tensor_board_writer.scalar_summary("dev_loss", np.exp(float(loss_total) / loss_count), step_count)
    

def main(args):
    tensor_board_writer = Logger()
    # Create model directory
    # if not os.path.exists(args.model_path):
    #     os.makedirs(args.model_path)
    
    # Image preprocessing, normalization for the pretrained resnet
    transform = transforms.Compose([ 
        transforms.RandomCrop(args.crop_size),
        transforms.RandomHorizontalFlip(), 
        transforms.ToTensor(), 
        transforms.Normalize((0.485, 0.456, 0.406), 
                             (0.229, 0.224, 0.225))])
    
    # Load vocabulary wrapper
    with open(args.vocab_path, 'rb') as f:
        vocab = pickle.load(f)
    
    with open(args.test_vocab_path, 'rb') as f:
        test_vocab = pickle.load(f)
    
    # Build data loader
    data_loader = get_loader(args.image_dir, args.caption_path, vocab, 
                             transform, args.batch_size,
                             shuffle=True, num_workers=args.num_workers) 
    
    test_data_loader = get_loader(
        args.test_image_dir, 
        args.test_caption_path, 
        test_vocab, 
        transform, 
        args.batch_size, 
        shuffle=True, 
        num_workers=args.num_workers)

    # Build the models
    encoder = EncoderCNN(args.embed_size).to(device)
    decoder = DecoderRNN(args.embed_size, args.hidden_size, len(vocab), args.num_layers).to(device)
    
    # Loss and optimizer
    criterion = nn.CrossEntropyLoss()
    params = list(decoder.parameters()) + list(encoder.linear.parameters()) + list(encoder.bn.parameters())
    optimizer = torch.optim.Adam(params, lr=args.learning_rate)
    
    # Train the models
    total_step = len(data_loader)
    for epoch in trange(args.num_epochs):
        for i, (images, captions, lengths) in enumerate(tqdm(data_loader)):
            
            # Set mini-batch dataset
            images = images.to(device)
            # print(images.shape)
            captions = captions.to(device)
            targets = pack_padded_sequence(captions, lengths, batch_first=True)[0]
            
            # Forward, backward and optimize
            features = encoder(images)
            outputs = decoder(features, captions, lengths)
            loss = criterion(outputs, targets)
            decoder.zero_grad()
            encoder.zero_grad()
            loss.backward()
            optimizer.step()

            # Print log info
            # if i % args.log_step == 0:
            #     if i != 0:
            #         step_count = epoch * total_step + i + 1
            #         perplexity_log = np.exp(loss.item())
            #         loss_log = loss.item()
            #         print(step_count, perplexity_log, loss_log)
            #         tensor_board_writer.scalar_summary("loss", loss_log, step_count)
            #         tensor_board_writer.scalar_summary("perplexity", perplexity_log, step_count)
            #     # log_generic_to_tensorboard(tensor_board_writer, step_count, "train", "loss", loss_log)
            #     # log_generic_to_tensorboard(tensor_board_writer, step_count, "train", "perplexity",perplexity_log)
            #     print('Epoch [{}/{}], Step [{}/{}], Loss: {:.4f}, Perplexity: {:5.4f}'
            #           .format(epoch, args.num_epochs, i, total_step, loss.item(), np.exp(loss.item())))
                      
                
            # Save the model checkpoints
        #     if (i+1) % args.save_step == 0:
        #         torch.save(decoder.state_dict(), os.path.join(
        #             args.model_path, 'decoder-{}-{}.ckpt'.format(epoch+1, i+1)))
        #         torch.save(encoder.state_dict(), os.path.join(
        #             args.model_path, 'encoder-{}-{}.ckpt'.format(epoch+1, i+1)))
            
        #     if torch.cuda.is_available():
        #         torch.cuda.empty_cache()
        # test(encoder, decoder, test_data_loader, (epoch) * total_step, tensor_board_writer)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model_path', type=str, default='models/' , help='path for saving trained models')
    parser.add_argument('--crop_size', type=int, default=224 , help='size for randomly cropping images')
    parser.add_argument('--vocab_path', type=str, default='data/vocab.pkl', help='path for vocabulary wrapper')
    parser.add_argument('--image_dir', type=str, default='data/resized2014', help='directory for resized images')
    parser.add_argument('--caption_path', type=str, default='data/annotations/captions_train2014.json', help='path for train annotation json file')
    parser.add_argument('--test_image_dir', type=str, default='data/val_resized2014', help='directory for resized images')
    parser.add_argument('--test_caption_path', type=str, default='data/annotations/captions_val2014.json', help='path for train annotation json file')
    parser.add_argument('--test_vocab_path', type=str, default='data/test_vocab.pkl', help='path for vocabulary wrapper')
    parser.add_argument('--log_step', type=int , default=10, help='step size for prining log info')
    parser.add_argument('--save_step', type=int , default=1000, help='step size for saving trained models')
    
    # Model parameters
    parser.add_argument('--embed_size', type=int , default=256, help='dimension of word embedding vectors')
    parser.add_argument('--hidden_size', type=int , default=512, help='dimension of lstm hidden states')
    parser.add_argument('--num_layers', type=int , default=1, help='number of layers in lstm')
    
    parser.add_argument('--num_epochs', type=int, default=5)
    parser.add_argument('--batch_size', type=int, default=128)
    parser.add_argument('--num_workers', type=int, default=2)
    parser.add_argument('--learning_rate', type=float, default=0.001)
    args = parser.parse_args()
    print(args)
    main(args)